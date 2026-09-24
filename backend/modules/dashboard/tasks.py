"""Deliver transactional notification events through live, push and e-mail channels."""

import asyncio
from datetime import UTC, datetime, timedelta
from html import escape

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.celery_app import celery_app
from core.database import AsyncSessionLocal
from core.live import publish_live_event
from core.logging import get_logger
from core.notifications import email_enabled, send_email, send_push_notification
from modules.auth.models import PushSubscription
from modules.dashboard.models import NotificationEvent

logger = get_logger(__name__)

MAX_ATTEMPTS = 5
BATCH_SIZE = 100


def push_targets(payload: dict, subscriptions: list) -> list:
    """Subscriptions a notification may be pushed to.

    Recipients are opt-in: `userId` / `userIds` address specific users, and only
    an explicit `broadcast` reaches every subscriber. An event without either
    (it used to go to everyone) is pushed to no one — paper decisions and other
    team-internal news must not reach all users of all events.
    """
    if payload.get("broadcast"):
        return list(subscriptions)
    user_ids = set(payload.get("userIds") or [])
    if payload.get("userId"):
        user_ids.add(payload["userId"])
    return [s for s in subscriptions if s.user_id in user_ids]


def _retry_delay(attempts: int) -> timedelta:
    """Exponential backoff: 30 s, 1 min, 2 min, 4 min, …"""
    return timedelta(seconds=30 * 2 ** max(0, attempts - 1))


async def _deliver(db: AsyncSession, item: NotificationEvent, subscriptions: list) -> list[str]:
    """Send one outbox item. Returns the ids of subscriptions that are gone.

    Raises when there were recipients but not a single send succeeded, so the
    item is retried.
    """
    payload = item.payload or {}
    if item.event_id and payload.get("publicLive"):
        await publish_live_event(item.event_id, item.event_type, payload)
    title = payload.get("title") or item.event_type.replace("_", " ").title()
    body = payload.get("message") or payload.get("body") or ""
    url = payload.get("url") or (f"/events/{item.event_id}/dashboard" if item.event_id else "/")

    targets = push_targets(payload, subscriptions) if body else []
    statuses = await asyncio.gather(
        *(send_push_notification(s.endpoint, s.p256dh, s.auth, title, body, url) for s in targets),
        return_exceptions=True,
    )
    gone = [s.id for s, status in zip(targets, statuses, strict=True) if status == "gone"]
    # "disabled" (no VAPID key) is not a failure of this message: push simply
    # is not a channel on this installation.
    attempted = [status for status in statuses if status not in ("gone", "disabled")]
    sent = sum(1 for status in attempted if status == "sent")

    emails = list(payload.get("emails") or [])
    if body and emails and email_enabled():
        ok = await send_email(emails, title, f"<p>{escape(body)}</p>".replace("\n", "<br>"), body)
        attempted.append("sent" if ok else "failed")
        sent += int(ok)

    if attempted and not sent:
        raise RuntimeError(f"delivery failed for all {len(attempted)} recipient(s)")
    return gone


async def deliver_pending(db: AsyncSession, now: datetime | None = None) -> int:
    """Deliver due outbox rows; returns how many were marked delivered.

    Rows are locked with ``SELECT … FOR UPDATE SKIP LOCKED`` (PostgreSQL; the
    clause is omitted on SQLite), so concurrent workers never pick up the same
    notification. A row is delivered when at least one send succeeded or it
    had no recipients; otherwise it is retried with backoff and marked
    ``failed`` after ``MAX_ATTEMPTS``. Subscriptions reported as expired
    (404/410) are deleted.
    """
    now = now or datetime.now(UTC)
    items = list(
        (
            await db.execute(
                select(NotificationEvent)
                .where(
                    NotificationEvent.status == "pending",
                    or_(
                        NotificationEvent.next_attempt_at.is_(None),
                        NotificationEvent.next_attempt_at <= now,
                    ),
                )
                .order_by(NotificationEvent.created_at)
                .limit(BATCH_SIZE)
                .with_for_update(skip_locked=True)
            )
        ).scalars()
    )
    if not items:
        return 0
    subscriptions = list((await db.execute(select(PushSubscription))).scalars())
    delivered = 0
    for item in items:
        item.attempts += 1
        try:
            gone = await _deliver(db, item, subscriptions)
        except Exception as exc:
            item.last_error = str(exc)[:2000]
            if item.attempts >= MAX_ATTEMPTS:
                item.status = "failed"
                item.processed_at = now
            else:
                item.next_attempt_at = now + _retry_delay(item.attempts)
            continue
        if gone:
            await db.execute(delete(PushSubscription).where(PushSubscription.id.in_(gone)))
            subscriptions = [s for s in subscriptions if s.id not in gone]
        item.status = "delivered"
        item.processed_at = now
        item.last_error = None
        delivered += 1
    await db.commit()
    return delivered


@celery_app.task(name="notifications.deliver_outbox")
def deliver_outbox() -> None:
    async def run() -> None:
        async with AsyncSessionLocal() as db:
            await deliver_pending(db)

    asyncio.run(run())


@celery_app.task(name="notifications.match_reminders")
def match_reminders() -> None:
    """Queue "match starts soon" pushes (runs every minute)."""
    from modules.events.notifications import queue_match_reminders

    async def run() -> None:
        async with AsyncSessionLocal() as db:
            queued = await queue_match_reminders(db)
            await db.commit()
            if queued:
                logger.info("match_reminders_queued", count=queued)

    asyncio.run(run())


@celery_app.task(name="notifications.deadline_reminders")
def deadline_reminders() -> None:
    """Queue reminders for deadlines due in 7, 3 and 1 day(s) (runs daily)."""
    from modules.events.notifications import queue_deadline_reminders

    async def run() -> None:
        async with AsyncSessionLocal() as db:
            queued = await queue_deadline_reminders(db)
            await db.commit()
            if queued:
                logger.info("deadline_reminders_queued", count=queued)

    asyncio.run(run())
