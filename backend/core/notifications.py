"""Email + Web Push notification helpers."""
import json
from typing import Any

import aiosmtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from core.config import get_settings
from core.logging import get_logger

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

async def send_push_notification(
    endpoint: str,
    p256dh: str,
    auth: str,
    title: str,
    body: str,
    url: str | None = None,
) -> bool:
    if not settings.vapid_private_key:
        return False
    try:
        from pywebpush import webpush, WebPushException

        subscription_info = {
            "endpoint": endpoint,
            "keys": {"p256dh": p256dh, "auth": auth},
        }
        data = json.dumps({"title": title, "body": body, "url": url})
        webpush(
            subscription_info=subscription_info,
            data=data,
            vapid_private_key=settings.vapid_private_key,
            vapid_claims={"sub": f"mailto:{settings.vapid_admin_email}"},
        )
        return True
    except Exception as exc:
        logger.warning("push_failed", error=str(exc), endpoint=endpoint[:40])
        return False
