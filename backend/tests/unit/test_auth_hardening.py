"""Login and configuration hardening (security review 2026-09, #13 and #14).

13. Unknown e-mail addresses skipped bcrypt (timing oracle for account
    enumeration), and bcrypt ran on the event loop.
14. APP_ENV values other than "production" skipped the production secret check.

Plus bcrypt 5, which refuses passwords over 72 bytes where bcrypt 4 cut them.
"""

import asyncio
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from pydantic import ValidationError

from core.config import Settings
from core.exceptions import UnauthorizedError
from modules.auth import service
from modules.auth.password_policy import MAX_BYTES, password_problem

# ── 13. Login timing and the event loop ───────────────────────────────────────


@pytest.mark.asyncio
async def test_unknown_email_still_costs_a_bcrypt_comparison(db, monkeypatch):
    compared: list[bytes] = []
    real = service.bcrypt.checkpw

    def counting_check(password: bytes, hashed: bytes) -> bool:
        compared.append(hashed)
        return real(password, hashed)

    monkeypatch.setattr(service.bcrypt, "checkpw", counting_check)
    with pytest.raises(UnauthorizedError):
        await service.authenticate_user(db, "nobody@test.com", "whatever-password")
    assert len(compared) == 1


async def _ticks_during(coro) -> int:
    """How often another coroutine got to run while `coro` was awaited."""
    ticks = 0
    done = False

    async def ticker():
        nonlocal ticks
        while not done:
            await asyncio.sleep(0.01)
            ticks += 1

    task = asyncio.create_task(ticker())
    await coro
    done = True
    await task
    return ticks


@pytest.mark.asyncio
async def test_bcrypt_does_not_block_the_event_loop(db, admin_user, monkeypatch):
    def slow_check(_password, _hashed):
        time.sleep(0.3)
        return True

    def slow_hash(_password, _salt):
        time.sleep(0.3)
        return b"$2b$12$" + b"x" * 53

    monkeypatch.setattr(service.bcrypt, "checkpw", slow_check)
    assert await _ticks_during(service.authenticate_user(db, admin_user.email, "pw")) >= 10
    monkeypatch.setattr(service.bcrypt, "hashpw", slow_hash)
    assert await _ticks_during(service.hash_password_async("new-password-123")) >= 10


# ── 14. APP_ENV ───────────────────────────────────────────────────────────────


@pytest.fixture
def clean_env(monkeypatch):
    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)


@pytest.mark.parametrize("app_env", ["prod", "staging", "Production", "test", "", "dev"])
def test_non_development_env_requires_production_secrets(clean_env, app_env):
    with pytest.raises(ValidationError):
        Settings(app_env=app_env, _env_file=None)


def test_development_env_is_normalised(clean_env):
    settings = Settings(app_env=" Development ", _env_file=None)
    assert settings.app_env == "development" and settings.is_dev


# ── bcrypt 5 and passwords over 72 bytes ──────────────────────────────────────

# Hashed by bcrypt 4.3.0, which silently used only the first 72 of its 86 bytes.
LEGACY_LONG_PASSWORD = (
    "correct horse battery staple – Grüße aus dem Turniersaal, 2025 edition!!" + "x" * 10
)
LEGACY_LONG_HASH = "$2b$04$Tl3WvJeUPyput3IUyJnzR.oezRFSZHTFQokzClfYof.FNa351Pise"


def test_bcrypt_4_hash_of_a_long_password_still_verifies():
    assert len(LEGACY_LONG_PASSWORD.encode()) > MAX_BYTES
    assert service.verify_password(LEGACY_LONG_PASSWORD, LEGACY_LONG_HASH)
    # bcrypt 4 semantics: only the first 72 bytes count.
    assert service.verify_password(LEGACY_LONG_PASSWORD[:-1] + "y", LEGACY_LONG_HASH)
    assert not service.verify_password("x" + LEGACY_LONG_PASSWORD[1:], LEGACY_LONG_HASH)


def test_hashing_a_long_password_is_refused_not_truncated():
    # The password policy keeps such passwords away from hash_password.
    with pytest.raises(ValueError):
        service.hash_password("a" * (MAX_BYTES + 1))
    assert service.verify_password("b" * MAX_BYTES, service.hash_password("b" * MAX_BYTES))


@pytest.mark.parametrize(
    ("password", "ok"),
    [
        ("Kiwi-Tram-" * 7 + "ab", True),  # exactly 72 bytes
        ("Kiwi-Tram-" * 7 + "abc", False),  # 73 bytes
        ("Grünkohl-" * 4 + "ä" * 30, False),  # 66 characters, 100 bytes
    ],
)
def test_policy_limits_bytes_not_characters(password, ok):
    problem = password_problem(password)
    assert (problem is None) is ok, problem
    if not ok:
        assert f"at most {MAX_BYTES} bytes" in problem


@pytest.mark.asyncio
async def test_long_password_at_login_is_a_normal_failure(db, admin_user, monkeypatch):
    compared: list[bytes] = []
    real = service.bcrypt.checkpw

    def recording_check(password: bytes, hashed: bytes) -> bool:
        compared.append(password)
        return real(password, hashed)

    monkeypatch.setattr(service.bcrypt, "checkpw", recording_check)
    for email in ("nobody@test.com", admin_user.email):
        with pytest.raises(UnauthorizedError):
            await service.authenticate_user(db, email, "ü" * 200)
    # The dummy-hash comparison for unknown accounts still runs, once each.
    assert len(compared) == 2
    assert all(len(password) == MAX_BYTES for password in compared)


def test_create_admin_refuses_a_long_password_even_in_development():
    backend = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, "scripts/create_admin.py", "--email", "admin@example.com"],
        cwd=backend,
        # The script puts /app (the image's code directory) on sys.path; outside
        # the image the backend directory has to be importable as well.
        env={
            **os.environ,
            "PYTHONPATH": str(backend),
            "APP_ENV": "development",
            "ADMIN_PASSWORD": "Kiwi-Tram-" * 8,
        },
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 1
    assert f"at most {MAX_BYTES} bytes" in result.stderr
