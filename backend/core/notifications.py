"""Email + Web Push notification helpers."""

import asyncio
import json
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Literal

import aiosmtplib

from core.config import get_settings
from core.logging import get_logger
from core.push_endpoints import push_endpoint_problem

settings = get_settings()
logger = get_logger(__name__)


# ── Email ─────────────────────────────────────────────────────────────────────


async def send_email(
    to: str | list[str],
    subject: str,
    html_body: str,
    text_body: str | None = None,
) -> bool:
    """Send via primary SMTP; fall back to SendGrid on failure."""
    recipients = [to] if isinstance(to, str) else to
    success = await _send_smtp(recipients, subject, html_body, text_body)
    if not success and settings.sendgrid_api_key:
        success = await _send_sendgrid(recipients, subject, html_body, text_body)
    return success


async def _send_smtp(
    recipients: list[str], subject: str, html_body: str, text_body: str | None
) -> bool:
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = settings.smtp_from
        msg["To"] = ", ".join(recipients)
        if text_body:
            msg.attach(MIMEText(text_body, "plain"))
        msg.attach(MIMEText(html_body, "html"))

        await aiosmtplib.send(
            msg,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_user or None,
            password=settings.smtp_password or None,
            start_tls=settings.smtp_tls,
        )
        logger.info("email_sent", to=recipients, subject=subject, via="smtp")
        return True
    except Exception as exc:
        logger.warning("smtp_failed", error=str(exc))
        return False


async def _send_sendgrid(
    recipients: list[str], subject: str, html_body: str, text_body: str | None
) -> bool:
    try:
        import httpx

        payload: dict[str, Any] = {
            "personalizations": [{"to": [{"email": r} for r in recipients]}],
            "from": {"email": settings.sendgrid_from},
            "subject": subject,
            "content": [{"type": "text/html", "value": html_body}],
        }
        if text_body:
            payload["content"].insert(0, {"type": "text/plain", "value": text_body})

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.sendgrid.com/v3/mail/send",
                headers={"Authorization": f"Bearer {settings.sendgrid_api_key}"},
                json=payload,
            )
            resp.raise_for_status()
        logger.info("email_sent", to=recipients, subject=subject, via="sendgrid")
        return True
    except Exception as exc:
        logger.error("sendgrid_failed", error=str(exc))
        return False


# ── Web Push ──────────────────────────────────────────────────────────────────


PushStatus = Literal["sent", "failed", "gone", "disabled"]


def email_enabled() -> bool:
    """Whether outgoing e-mail is configured (same rule as account-creation mail)."""
    return bool(settings.smtp_host) and not settings.is_dev


async def send_push_notification(
    endpoint: str,
    p256dh: str,
    auth: str,
    title: str,
    body: str,
    url: str | None = None,
) -> PushStatus:
    """Send one Web Push message.

    Returns ``"sent"`` on success, ``"gone"`` when the push service reports the
    subscription as expired (HTTP 404/410 — the caller should delete it),
    ``"failed"`` for any other error (worth a retry) and ``"disabled"`` when no
    VAPID key is configured.
    """
    if not settings.vapid_private_key:
        return "disabled"
    problem = push_endpoint_problem(endpoint)
    if problem:
        # Saved before the subscription route checked endpoints (SSRF): never
        # contacted, and "gone" makes the caller delete the subscription.
        logger.warning("push_endpoint_refused", reason=problem, endpoint=endpoint[:40])
        return "gone"
    try:
        from pywebpush import WebPushException, webpush
    except ImportError:  # pragma: no cover - dependency is installed in production
        return "disabled"

    subscription_info = {
        "endpoint": endpoint,
        "keys": {"p256dh": p256dh, "auth": auth},
    }
    data = json.dumps({"title": title, "body": body, "url": url})
    try:
        # pywebpush is synchronous (requests); keep it off the event loop.
        await asyncio.to_thread(
            webpush,
            subscription_info=subscription_info,
            data=data,
            vapid_private_key=settings.vapid_private_key,
            vapid_claims={"sub": f"mailto:{settings.vapid_admin_email}"},
        )
        return "sent"
    except WebPushException as exc:
        status_code = getattr(getattr(exc, "response", None), "status_code", None)
        if status_code in (404, 410):
            logger.info("push_subscription_gone", endpoint=endpoint[:40], status=status_code)
            return "gone"
        logger.warning("push_failed", error=str(exc), endpoint=endpoint[:40])
        return "failed"
    except Exception as exc:
        logger.warning("push_failed", error=str(exc), endpoint=endpoint[:40])
        return "failed"
