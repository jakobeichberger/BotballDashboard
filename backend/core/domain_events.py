"""Central event-trigger entry point backed by a transactional outbox."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.auth.models import User
from modules.dashboard.models import NotificationEvent, NotificationRecipient
from modules.dashboard.notifications import recipients_of


async def emit_event(
    db: AsyncSession,
    event_type: str,
    *,
    event_id: str | None = None,
    payload: dict | None = None,
    dedupe_key: str | None = None,
) -> NotificationEvent | None:
    """Queue a notification in the outbox (delivered by the worker after commit).

    With ``dedupe_key`` the notification is queued at most once: if a row with
    that key already exists, nothing is added and ``None`` is returned. The
    column is unique, so a concurrent duplicate fails that transaction instead
    of reaching recipients twice.

    The addressees (``userId``/``userIds``, or everyone for ``broadcast``) are
    recorded in ``notification_recipients`` in the same transaction, which is
    what the in-app notification center reads.
    """
    if dedupe_key is not None:
        existing = await db.execute(
            select(NotificationEvent.id).where(NotificationEvent.dedupe_key == dedupe_key)
        )
        if existing.scalar_one_or_none():
            return None
    payload = payload or {}
    now = datetime.now(UTC)
    item = NotificationEvent(
        event_id=event_id,
        event_type=event_type,
        payload=payload,
        dedupe_key=dedupe_key,
        created_at=now,
    )
    db.add(item)
    await db.flush()
    addressed: list[str | None] = [None]
    if not payload.get("broadcast"):
        addressed = []
        wanted = recipients_of(payload)
        if wanted:
            # Only existing accounts: a stale id must not fail the whole write.
            existing = await db.execute(select(User.id).where(User.id.in_(wanted)))
            addressed.extend(sorted(existing.scalars()))
    db.add_all(
        NotificationRecipient(notification_id=item.id, user_id=user_id, created_at=now)
        for user_id in addressed
    )
    await db.flush()
    return item
