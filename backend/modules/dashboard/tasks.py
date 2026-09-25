"""Deliver transactional notification events through live, push and e-mail channels."""

import asyncio
from datetime import UTC, datetime, timedelta
from html import escape

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.celery_app import celery_app
from core.database import AsyncSessionLocal
from core.live import publish_live_event
from core.logging import get_logger
from core.mail_templates import DEFAULT_LANGUAGE, normalize_language, render_notification
from core.notifications import email_enabled, send_email, send_push_notification
from modules.auth.models import PushSubscription, User
from modules.dashboard.models import NotificationEvent
from modules.dashboard.notifications import category_of, recipients_of, wants_push
from modules.teams.models import TeamMember

logger = get_logger(__name__)

MAX_ATTEMPTS = 5
BATCH_SIZE = 100


def push_targets(
    payload: dict,
    subscriptions: list,
    *,
    event_type: str = "",
    preferences: dict[str, dict] | None = None,
) -> list:
    """Subscriptions a notification may be pushed to.

    Recipients are opt-in: `userId` / `userIds` address specific users, and only
    an explicit `broadcast` reaches every subscriber. An event without either
    (it used to go to everyone) is pushed to no one — paper decisions and other
    team-internal news must not reach all users of all events.

    `preferences` maps user id → that user's notification preferences; users
    who muted the event's category are skipped.
    """
    if payload.get("broadcast"):
        addressed = list(subscriptions)
    else:
        user_ids = recipients_of(payload)
        addressed = [s for s in subscriptions if s.user_id in user_ids]
    category = category_of(event_type, payload)
    prefs = preferences or {}
    return [s for s in addressed if wants_push(prefs.get(s.user_id), category)]


async def load_preferences(db: AsyncSession, subscriptions: list) -> dict[str, dict]:
    """Notification preferences of every user owning one of `subscriptions`."""
    user_ids = {s.user_id for s in subscriptions}
    if not user_ids:
        return {}
    rows = await db.execute(
        select(User.id, User.notification_preferences).where(User.id.in_(user_ids))
    )
    return {user_id: prefs or {} for user_id, prefs in rows}


async def load_languages(db: AsyncSession, subscriptions: list) -> dict[str, str]:
    """Profile language of every user owning one of `subscriptions`."""
    user_ids = {s.user_id for s in subscriptions}
    if not user_ids:
        return {}
    rows = await db.execute(select(User.id, User.preferred_language).where(User.id.in_(user_ids)))
    return {user_id: normalize_language(language) for user_id, language in rows}


async def recipient_languages(db: AsyncSession, emails: list[str]) -> dict[str, str]:
    """E-mail address → language of the account behind it.

    An address belongs to an account either directly (User.email) or through
    a team member linked to an account (TeamMember.email + user_id). Addresses
    without an account get DEFAULT_LANGUAGE.
    """
    wanted = sorted({email.lower() for email in emails})
    found: dict[str, str] = {}
    if wanted:
        direct = await db.execute(
            select(User.email, User.preferred_language).where(func.lower(User.email).in_(wanted))
        )
        for email, language in direct:
            found[email.lower()] = language
        members = await db.execute(
            select(TeamMember.email, User.preferred_language)
            .join(User, User.id == TeamMember.user_id)
            .where(func.lower(TeamMember.email).in_(wanted))
        )
        for member_email, language in members:
            if member_email:
                found.setdefault(member_email.lower(), language)
    return {
        email: normalize_language(found.get(email.lower()), DEFAULT_LANGUAGE) for email in emails
    }


async def _send_localized_emails(db: AsyncSession, payload: dict, emails: list[str]) -> list[bool]:
    """Send a templated notification once per recipient language."""
    by_language: dict[str, list[str]] = {}
    for email, language in (await recipient_languages(db, emails)).items():
        by_language.setdefault(language, []).append(email)
    results = []
    for language, recipients in sorted(by_language.items()):
        message = render_notification(payload, language)
        if message is None:  # pragma: no cover - callers check for a template
            continue
        results.append(await send_email(recipients, message.subject, message.html, message.text))
    return results


def _retry_delay(attempts: int) -> timedelta:
    """Exponential backoff: 30 s, 1 min, 2 min, 4 min, …"""
    return timedelta(seconds=30 * 2 ** max(0, attempts - 1))


async def _deliver(
    db: AsyncSession,
    item: NotificationEvent,
    subscriptions: list,
    preferences: dict[str, dict] | None = None,
    languages: dict[str, str] | None = None,
) -> list[str]:
    """Send one outbox item. Returns the ids of subscriptions that are gone.

    Push goes only to recipients who have not muted the item's category
    (`preferences`, see modules.dashboard.notifications). Items with an
    ``i18n`` template are pushed and mailed in each recipient's language
    (`languages`: user id → language; mail addresses are looked up).

    Raises when there were recipients but not a single send succeeded, so the
    item is retried.
    """
    payload = item.payload or {}
    if item.event_id and payload.get("publicLive"):
        await publish_live_event(item.event_id, item.event_type, payload)
    title = payload.get("title") or item.event_type.replace("_", " ").title()
    body = payload.get("message") or payload.get("body") or ""
    url = payload.get("url") or (f"/events/{item.event_id}/dashboard" if item.event_id else "/")

    targets = (
        push_targets(payload, subscriptions, event_type=item.event_type, preferences=preferences)
        if body
        else []
    )

    def localized(subscription) -> tuple[str, str]:
        language = (languages or {}).get(subscription.user_id, DEFAULT_LANGUAGE)
        message = render_notification(payload, language)
        return (message.subject, message.summary) if message else (title, body)

    statuses = await asyncio.gather(
        *(
            send_push_notification(s.endpoint, s.p256dh, s.auth, *localized(s), url)
            for s in targets
        ),
        return_exceptions=True,
    )
    gone = [s.id for s, status in zip(targets, statuses, strict=True) if status == "gone"]
    # "disabled" (no VAPID key) is not a failure of this message: push simply
    # is not a channel on this installation.
    attempted = [status for status in statuses if status not in ("gone", "disabled")]
    sent = sum(1 for status in attempted if status == "sent")

    emails = list(payload.get("emails") or [])
    if emails and email_enabled() and render_notification(payload, DEFAULT_LANGUAGE):
        for ok in await _send_localized_emails(db, payload, emails):
            attempted.append("sent" if ok else "failed")
            sent += int(ok)
    elif body and emails and email_enabled():
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
    preferences = await load_preferences(db, subscriptions)
    languages = await load_languages(db, subscriptions)
    delivered = 0
    for item in items:
        item.attempts += 1
        try:
            gone = await _deliver(db, item, subscriptions, preferences, languages)
        except Exception as exc:  # noqa: BLE001 - recorded on the item and retried
            logger.warning(
                "notification_delivery_failed",
                outbox_id=str(item.id),
                attempt=item.attempts,
                error=str(exc),
            )
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
