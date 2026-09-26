"""Account mails: queued after the commit, never logged with a token in production.

* The password-reset link only goes to the log in development; elsewhere a
  missing mail setup is a warning without the token (a logged link is a
  logged account takeover).
* A SendGrid-only setup counts as "mail configured" and really sends.
* The mails leave after the commit and the response does not wait for them,
  so a slow or dead SMTP server neither hangs the request nor tells an
  anonymous caller (by timing) whether an address has an account.
"""

import asyncio
import time
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

import core.notifications as notifications
from core.config import get_settings
from core.database import get_db
from core.task_queue import drain_pending_tasks
from main import app
from modules.auth import routes as auth_routes
from modules.auth.models import User
from modules.auth.service import hash_password


class _Spy:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict]] = []

    def _record(self, level: str):
        def log(event, **kw):
            self.calls.append((level, event, kw))

        return log

    def __getattr__(self, level: str):
        return self._record(level)


@pytest_asyncio.fixture
async def committing_client(db) -> AsyncGenerator[AsyncClient]:
    """Like ``client``, but the request session commits in the teardown as in production."""

    async def override_get_db():
        yield db
        await db.commit()

    app.dependency_overrides[get_db] = override_get_db
    app.state.testing = True
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
    app.state.testing = False


@pytest_asyncio.fixture
async def known_user(db) -> User:
    user = User(
        email="known@example.com",
        display_name="Known",
        hashed_password=hash_password("password123"),
        is_active=True,
    )
    db.add(user)
    await db.commit()
    return user


# ── Reset link in the log ─────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("app_env", ["production", "test"])
async def test_reset_link_is_not_logged_outside_development(monkeypatch, app_env):
    monkeypatch.setattr(get_settings(), "app_env", app_env)
    monkeypatch.setattr(get_settings(), "smtp_host", "")
    monkeypatch.setattr(get_settings(), "sendgrid_api_key", "")
    spy = _Spy()
    monkeypatch.setattr(auth_routes, "logger", spy)

    await auth_routes.send_password_reset_email("a@example.com", "A", "SECRET-TOKEN")

    assert spy.calls, "a missing mail setup must at least be reported"
    for _level, event, kw in spy.calls:
        assert event != "password_reset_link"
        assert "SECRET-TOKEN" not in repr(kw)
    assert any(
        level == "warning" and event == "password_reset_mail_unavailable"
        for level, event, _ in spy.calls
    )


@pytest.mark.asyncio
async def test_reset_link_is_logged_in_development(monkeypatch):
    monkeypatch.setattr(get_settings(), "app_env", "development")
    spy = _Spy()
    monkeypatch.setattr(auth_routes, "logger", spy)
    await auth_routes.send_password_reset_email("a@example.com", "A", "DEV-TOKEN")
    [(level, event, kw)] = spy.calls
    assert event == "password_reset_link" and "token=DEV-TOKEN" in kw["link"]


# ── SendGrid-only setups ──────────────────────────────────────────────────────


def test_sendgrid_only_counts_as_mail_configured(monkeypatch):
    monkeypatch.setattr(get_settings(), "app_env", "production")
    monkeypatch.setattr(get_settings(), "smtp_host", "")
    monkeypatch.setattr(get_settings(), "sendgrid_api_key", "SG.key")
    assert notifications.email_enabled() is True
    assert auth_routes._mail_enabled() is True
    monkeypatch.setattr(get_settings(), "sendgrid_api_key", "")
    assert notifications.email_enabled() is False
    assert auth_routes._mail_enabled() is False


@pytest.mark.asyncio
async def test_sendgrid_only_setup_sends_the_reset_mail(monkeypatch):
    monkeypatch.setattr(get_settings(), "app_env", "production")
    monkeypatch.setattr(get_settings(), "smtp_host", "")
    monkeypatch.setattr(get_settings(), "sendgrid_api_key", "SG.key")
    smtp_calls: list = []
    sendgrid_calls: list = []

    async def fake_smtp(*args, **kwargs):
        smtp_calls.append(args)
        return False

    async def fake_sendgrid(recipients, subject, html, text):
        sendgrid_calls.append((recipients, text))
        return True

    monkeypatch.setattr(notifications, "_send_smtp", fake_smtp)
    monkeypatch.setattr(notifications, "_send_sendgrid", fake_sendgrid)
    await auth_routes.send_password_reset_email("a@example.com", "A", "TOK")
    # No SMTP host: straight to SendGrid, no doomed connection attempt first.
    assert smtp_calls == []
    [(recipients, text)] = sendgrid_calls
    assert recipients == ["a@example.com"] and "token=TOK" in text


@pytest.mark.asyncio
async def test_smtp_send_has_a_timeout(monkeypatch):
    monkeypatch.setattr(get_settings(), "smtp_host", "mail.test")
    options: dict = {}

    async def fake_send(message, **kw):
        options.update(kw)

    monkeypatch.setattr(notifications.aiosmtplib, "send", fake_send)
    assert await notifications.send_email("a@example.com", "S", "<p>x</p>", "x") is True
    assert 0 < options["timeout"] <= 30


# ── The response does not wait for the mail ──────────────────────────────────


@pytest.mark.asyncio
async def test_reset_response_does_not_wait_for_a_slow_mailer(
    committing_client, known_user, monkeypatch
):
    slow = 1.5
    sent: list[str] = []

    async def slow_mail(email, display_name, token, language=None):
        await asyncio.sleep(slow)
        sent.append(email)

    monkeypatch.setattr(auth_routes, "send_password_reset_email", slow_mail)

    async def timed(email: str) -> float:
        started = time.perf_counter()
        resp = await committing_client.post(
            "/api/auth/password-reset/request", json={"email": email}
        )
        assert resp.status_code == 204
        return time.perf_counter() - started

    unknown = await timed("nobody@example.com")
    known = await timed(known_user.email)
    # Neither answer waits for the mailer, so timing reveals nothing.
    assert known < slow / 2, known
    assert abs(known - unknown) < slow / 3, (known, unknown)
    # The mail still goes out, after the commit.
    await drain_pending_tasks()
    assert sent == [known_user.email]


@pytest.mark.asyncio
async def test_reset_mail_is_not_sent_when_the_transaction_rolls_back(
    client, db, known_user, monkeypatch
):
    sent: list[str] = []

    async def capture(email, display_name, token, language=None):
        sent.append(email)

    monkeypatch.setattr(auth_routes, "send_password_reset_email", capture)
    resp = await client.post("/api/auth/password-reset/request", json={"email": known_user.email})
    assert resp.status_code == 204
    await db.rollback()
    await db.commit()
    await drain_pending_tasks()
    assert sent == []


@pytest.mark.asyncio
async def test_account_mail_does_not_hold_the_create_response(
    committing_client, auth_headers, monkeypatch
):
    slow = 1.5
    sent: list[str] = []

    async def slow_mail(email, display_name, language):
        await asyncio.sleep(slow)
        sent.append(email)

    monkeypatch.setattr(auth_routes, "_mail_enabled", lambda: True)
    monkeypatch.setattr(auth_routes, "send_account_created_email", slow_mail)
    started = time.perf_counter()
    resp = await committing_client.post(
        "/api/auth/users",
        json={"email": "fresh@example.org", "display_name": "F", "password": "correct-horse-1"},
        headers=auth_headers,
    )
    elapsed = time.perf_counter() - started
    assert resp.status_code == 201, resp.text
    assert elapsed < slow / 2, elapsed
    await drain_pending_tasks()
    assert sent == ["fresh@example.org"]
