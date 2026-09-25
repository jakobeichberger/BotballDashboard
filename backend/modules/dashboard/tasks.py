"""Deliver transactional notification events through live, push and e-mail channels."""

import asyncio
from datetime import UTC, datetime, timedelta
from html import escape

from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.celery_app import celery_app, run_task
from core.database import WorkerSessionLocal
from core.live import publish_live_event
from core.logging import get_logger
from core.mail_templates import DEFAULT_LANGUAGE, normalize_language, render_notification
from core.notifications import email_enabled, send_email, send_push_notification
from modules.auth.models import PushSubscription, User
from modules.dashboard.models import (
    OPEN_OUTBOX_STATUSES,
    NotificationEvent,
    NotificationRead,
    NotificationRecipient,
)
from modules.dashboard.notifications import category_of, recipients_of, wants_push
from modules.teams.models import TeamMember

logger = get_logger(__name__)

MAX_ATTEMPTS = 5
BATCH_SIZE = 100
#: How long a claimed row stays reserved for the worker that claimed it. Longer
#: than the Celery task time limit (core.celery_app), so a row is never
#: claimed again while its worker may still be sending; a worker that died
#: mid-batch leaves "sending" rows that are due again once the lease ends.
CLAIM_LEASE = timedelta(minutes=10)
#: Delivered and failed outbox rows are kept this long (notification center,
#: debugging), then removed by cleanup_outbox.
OUTBOX_RETENTION = timedelta(days=30)


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


async def _send_localized_emails(
    payload: dict, emails: list[str], email_languages: dict[str, str]
) -> list[bool]:
    """Send a templated notification once per recipient language."""
    by_language: dict[str, list[str]] = {}
    for email in emails:
        language = email_languages.get(email, DEFAULT_LANGUAGE)
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
    item: NotificationEvent,
    subscriptions: list,
    preferences: dict[str, dict] | None = None,
    languages: dict[str, str] | None = None,
    email_languages: dict[str, str] | None = None,
) -> list[str]:
    """Send one outbox item. Returns the ids of subscriptions that are gone.

    Push goes only to recipients who have not muted the item's category
    (`preferences`, see modules.dashboard.notifications). Items with an
    ``i18n`` template are pushed and mailed in each recipient's language
    (`languages`: user id → language; `email_languages`: address → language).
    Runs outside any database transaction: everything it needs is loaded
    beforehand.

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
        for ok in await _send_localized_emails(payload, emails, email_languages or {}):
            attempted.append("sent" if ok else "failed")
            sent += int(ok)
    elif body and emails and email_enabled():
        ok = await send_email(emails, title, f"<p>{escape(body)}</p>".replace("\n", "<br>"), body)
        attempted.append("sent" if ok else "failed")
        sent += int(ok)

    if attempted and not sent:
        raise RuntimeError(f"delivery failed for all {len(attempted)} recipient(s)")
    return gone


def _due(now: datetime):
    """Rows to deliver now: pending and due, or claimed by a worker whose lease ran out."""
    status = NotificationEvent.status
    due_at = NotificationEvent.next_attempt_at
    return and_(
        # Spelled out so PostgreSQL can use the partial index ix_notification_events_due.
        status.in_(OPEN_OUTBOX_STATUSES),
        or_(
            and_(status == "pending", or_(due_at.is_(None), due_at <= now)),
            and_(status == "sending", due_at <= now),
        ),
    )


async def claim_batch(db: AsyncSession, now: datetime) -> list[NotificationEvent]:
    """Claim up to BATCH_SIZE due rows for this worker and commit the claim.

    Rows are locked with ``SELECT … FOR UPDATE SKIP LOCKED`` (PostgreSQL; the
    clause is omitted on SQLite) only for this short transaction: they are
    marked ``sending`` with a lease (CLAIM_LEASE) and the attempt is counted,
    so concurrent workers skip them without a lock being held while this one
    talks to push services and mail servers.
    """
    items = list(
        (
            await db.execute(
                select(NotificationEvent)
                .where(_due(now))
                .order_by(NotificationEvent.created_at)
                .limit(BATCH_SIZE)
                .with_for_update(skip_locked=True)
            )
        ).scalars()
    )
    for item in items:
        item.status = "sending"
        item.attempts += 1
        item.next_attempt_at = now + CLAIM_LEASE
    await db.commit()
    return items


async def _load_subscriptions(db: AsyncSession, items: list[NotificationEvent]) -> list:
    """Push subscriptions of the batch's recipients (all of them only for a broadcast)."""
    payloads = [item.payload or {} for item in items]
    if any(payload.get("broadcast") for payload in payloads):
        query = select(PushSubscription)
    else:
        user_ids = set().union(*(recipients_of(payload) for payload in payloads))
        if not user_ids:
            return []
        query = select(PushSubscription).where(PushSubscription.user_id.in_(user_ids))
    return list((await db.execute(query)).scalars())


async def deliver_pending(db: AsyncSession, now: datetime | None = None) -> int:
    """Deliver due outbox rows; returns how many were marked delivered.

    Three steps, none of which holds a transaction open during network I/O:

    1. claim a batch (claim_batch) and commit;
    2. load what the sends need (subscriptions of the recipients, their
       preferences and languages), end that read transaction, then send;
    3. record the outcomes and commit.

    A row is delivered when at least one send succeeded or it had no
    recipients; otherwise it is retried with backoff and marked ``failed``
    after ``MAX_ATTEMPTS``. Subscriptions reported as expired (404/410) are
    deleted.
    """
    now = now or datetime.now(UTC)
    items = await claim_batch(db, now)
    if not items:
        return 0

    subscriptions = await _load_subscriptions(db, items)
    preferences = await load_preferences(db, subscriptions)
    languages = await load_languages(db, subscriptions)
    emails = sorted({email for item in items for email in (item.payload or {}).get("emails") or []})
    email_languages = await recipient_languages(db, emails) if emails else {}
    await db.commit()  # end the read transaction before the network sends

    outcomes: list[tuple[NotificationEvent, Exception | None]] = []
    gone_ids: set[str] = set()
    for item in items:
        live_subscriptions = [s for s in subscriptions if s.id not in gone_ids]
        try:
            gone = await _deliver(item, live_subscriptions, preferences, languages, email_languages)
        except Exception as exc:  # noqa: BLE001 - recorded on the item and retried
            logger.warning(
                "notification_delivery_failed",
                outbox_id=str(item.id),
                attempt=item.attempts,
                error=str(exc),
            )
            outcomes.append((item, exc))
            continue
        gone_ids.update(gone)
        outcomes.append((item, None))

    delivered = 0
    for item, error in outcomes:
        if error is not None:
            item.last_error = str(error)[:2000]
            if item.attempts >= MAX_ATTEMPTS:
                item.status = "failed"
                item.processed_at = now
            else:
                item.status = "pending"
                item.next_attempt_at = now + _retry_delay(item.attempts)
            continue
        item.status = "delivered"
        item.processed_at = now
        item.next_attempt_at = None
        item.last_error = None
        delivered += 1
    if gone_ids:
        await db.execute(delete(PushSubscription).where(PushSubscription.id.in_(gone_ids)))
    await db.commit()
    return delivered


async def cleanup_outbox(db: AsyncSession, now: datetime | None = None) -> int:
    """Delete delivered and failed outbox rows older than OUTBOX_RETENTION.

    Their recipient and read rows go with them (explicitly, so this does not
    depend on the database enforcing ON DELETE CASCADE). Returns the number of
    outbox rows removed.
    """
    cutoff = (now or datetime.now(UTC)) - OUTBOX_RETENTION
    old = select(NotificationEvent.id).where(
        NotificationEvent.status.in_(("delivered", "failed")),
        NotificationEvent.created_at < cutoff,
    )
    await db.execute(
        delete(NotificationRecipient).where(NotificationRecipient.notification_id.in_(old))
    )
    await db.execute(delete(NotificationRead).where(NotificationRead.notification_id.in_(old)))
    result = await db.execute(delete(NotificationEvent).where(NotificationEvent.id.in_(old)))
    await db.commit()
    return int(getattr(result, "rowcount", 0) or 0)


@celery_app.task(name="notifications.deliver_outbox")
def deliver_outbox() -> None:
    async def run() -> None:
        async with WorkerSessionLocal() as db:
            await deliver_pending(db)

    run_task(run)


@celery_app.task(name="notifications.cleanup_outbox")
def cleanup_outbox_task() -> None:
    """Remove outbox history older than OUTBOX_RETENTION (runs daily)."""

    async def run() -> None:
        async with WorkerSessionLocal() as db:
            removed = await cleanup_outbox(db)
            if removed:
                logger.info("outbox_cleaned", count=removed)

    run_task(run)


@celery_app.task(name="notifications.match_reminders")
def match_reminders() -> None:
    """Queue "match starts soon" pushes (runs every minute)."""
    from modules.events.notifications import queue_match_reminders

    async def run() -> None:
        async with WorkerSessionLocal() as db:
            queued = await queue_match_reminders(db)
            await db.commit()
            if queued:
                logger.info("match_reminders_queued", count=queued)

    run_task(run)


@celery_app.task(name="notifications.deadline_reminders")
def deadline_reminders() -> None:
    """Queue reminders for deadlines due in 7, 3 and 1 day(s) (runs daily)."""
    from modules.events.notifications import queue_deadline_reminders

    async def run() -> None:
        async with WorkerSessionLocal() as db:
            queued = await queue_deadline_reminders(db)
            await db.commit()
            if queued:
                logger.info("deadline_reminders_queued", count=queued)

    run_task(run)
