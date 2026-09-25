"""Login and configuration hardening (security review 2026-09, #13 and #14).

13. Unknown e-mail addresses skipped bcrypt (timing oracle for account
    enumeration), and bcrypt ran on the event loop.
14. APP_ENV values other than "production" skipped the production secret check.
"""

import asyncio
import time

import pytest
from pydantic import ValidationError

from core.config import Settings
from core.exceptions import UnauthorizedError
from modules.auth import service

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
