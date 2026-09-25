"""core.notifications: e-mail over SMTP with SendGrid fallback, and Web Push.

The transports are replaced by fakes (aiosmtplib.send, httpx.AsyncClient,
pywebpush.webpush); what is checked is what the helpers hand them and how
they report failures to the outbox.
"""

import json
from email.message import Message

import pytest

from core import notifications


@pytest.fixture
def configure(monkeypatch):
    def apply(**values):
        monkeypatch.setattr(
            notifications, "settings", notifications.settings.model_copy(update=values)
        )

    return apply


# ── E-mail ────────────────────────────────────────────────────────────────────


def _parts(message: Message) -> dict[str, str]:
    return {
        part.get_content_type(): part.get_payload(decode=True).decode()
        for part in message.walk()
        if not part.is_multipart()
    }


async def test_smtp_sends_html_and_text_alternatives(configure, monkeypatch):
    configure(
        smtp_host="mail.test",
        smtp_port=2525,
        smtp_user="bot",
        smtp_password="secret",
        smtp_from="Botball <noreply@botball.test>",
        smtp_tls=False,
    )
    sent: list[tuple[Message, dict]] = []

    async def fake_send(message, **options):
        sent.append((message, options))

    monkeypatch.setattr(notifications.aiosmtplib, "send", fake_send)

    ok = await notifications.send_email(
        ["a@botball.test", "b@botball.test"], "Hello", "<p>Hi</p>", "Hi"
    )

    assert ok is True
    [(message, options)] = sent
    assert message["To"] == "a@botball.test, b@botball.test"
    assert message["From"] == "Botball <noreply@botball.test>"
    assert _parts(message) == {"text/plain": "Hi", "text/html": "<p>Hi</p>"}
    assert options == {
        "hostname": "mail.test",
        "port": 2525,
        "username": "bot",
        "password": "secret",
        "start_tls": False,
    }


async def test_smtp_failure_without_sendgrid_reports_false(configure, monkeypatch):
    configure(smtp_host="mail.test", sendgrid_api_key="")

    async def refused(message, **options):
        raise ConnectionRefusedError("no mail server")

    monkeypatch.setattr(notifications.aiosmtplib, "send", refused)
    assert await notifications.send_email("a@botball.test", "S", "<p>x</p>") is False


class _FakeResponse:
    def __init__(self, status: int):
        self.status = status

    def raise_for_status(self) -> None:
        if self.status >= 400:
            raise RuntimeError(f"HTTP {self.status}")


class _FakeClient:
    """Records the SendGrid request made through httpx.AsyncClient."""

    requests: list[dict] = []
    status = 202

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, headers, json):
        type(self).requests.append({"url": url, "headers": headers, "json": json})
        return _FakeResponse(type(self).status)


@pytest.fixture
def sendgrid(configure, monkeypatch):
    import httpx

    configure(
        smtp_host="mail.test", sendgrid_api_key="SG.key", sendgrid_from="noreply@botball.test"
    )

    async def refused(message, **options):
        raise ConnectionRefusedError("no mail server")

    monkeypatch.setattr(notifications.aiosmtplib, "send", refused)
    _FakeClient.requests = []
    _FakeClient.status = 202
    monkeypatch.setattr(httpx, "AsyncClient", _FakeClient)
    return _FakeClient


async def test_sendgrid_is_the_fallback_when_smtp_fails(sendgrid):
    ok = await notifications.send_email(["a@botball.test"], "Subject", "<p>Body</p>", "Body")

    assert ok is True
    [request] = sendgrid.requests
    assert request["url"] == "https://api.sendgrid.com/v3/mail/send"
    assert request["headers"] == {"Authorization": "Bearer SG.key"}
    payload = request["json"]
    assert payload["from"] == {"email": "noreply@botball.test"}
    assert payload["personalizations"] == [{"to": [{"email": "a@botball.test"}]}]
    # Plain text first, as the MIME alternative order requires.
    assert [c["type"] for c in payload["content"]] == ["text/plain", "text/html"]


async def test_sendgrid_error_reports_false(sendgrid):
    sendgrid.status = 401
    assert await notifications.send_email("a@botball.test", "S", "<p>x</p>") is False


def test_email_enabled_needs_smtp_outside_development(configure):
    configure(smtp_host="", app_env="production")
    assert notifications.email_enabled() is False
    configure(smtp_host="mail.test", app_env="development")
    assert notifications.email_enabled() is False
    configure(smtp_host="mail.test", app_env="production")
    assert notifications.email_enabled() is True


# ── Web Push ──────────────────────────────────────────────────────────────────


async def _push():
    return await notifications.send_push_notification(
        "https://fcm.googleapis.com/fcm/send/123", "p256dh-key", "auth-key", "Title", "Body", "/e/1"
    )


async def test_push_to_an_unknown_host_is_refused_as_gone(configure, monkeypatch):
    import pywebpush

    configure(vapid_private_key="/app/vapid/private_key.pem")
    monkeypatch.setattr(pywebpush, "webpush", lambda **_kwargs: pytest.fail("contacted"))
    result = await notifications.send_push_notification(
        "https://push.example/endpoint/123", "p256dh-key", "auth-key", "Title", "Body"
    )
    assert result == "gone"


async def test_push_is_disabled_without_vapid_key(configure):
    configure(vapid_private_key="")
    assert await _push() == "disabled"


@pytest.fixture
def webpush(configure, monkeypatch):
    import pywebpush

    configure(vapid_private_key="/app/vapid/private_key.pem", vapid_admin_email="ops@botball.test")
    calls: list[dict] = []
    outcome: dict = {"raise": None}

    def fake_webpush(**kwargs):
        calls.append(kwargs)
        if outcome["raise"] is not None:
            raise outcome["raise"]

    monkeypatch.setattr(pywebpush, "webpush", fake_webpush)
    return calls, outcome


async def test_push_sent_with_payload_and_vapid_claims(webpush):
    calls, _ = webpush
    assert await _push() == "sent"
    [call] = calls
    assert call["subscription_info"] == {
        "endpoint": "https://fcm.googleapis.com/fcm/send/123",
        "keys": {"p256dh": "p256dh-key", "auth": "auth-key"},
    }
    assert json.loads(call["data"]) == {"title": "Title", "body": "Body", "url": "/e/1"}
    assert call["vapid_private_key"] == "/app/vapid/private_key.pem"
    assert call["vapid_claims"] == {"sub": "mailto:ops@botball.test"}


class _Response:
    def __init__(self, status_code: int):
        self.status_code = status_code


@pytest.mark.parametrize("status, expected", [(410, "gone"), (404, "gone"), (500, "failed")])
async def test_push_service_errors(webpush, status, expected):
    from pywebpush import WebPushException

    _, outcome = webpush
    outcome["raise"] = WebPushException("rejected", response=_Response(status))
    assert await _push() == expected


async def test_push_transport_error_is_failed(webpush):
    _, outcome = webpush
    outcome["raise"] = ConnectionError("network down")
    assert await _push() == "failed"
