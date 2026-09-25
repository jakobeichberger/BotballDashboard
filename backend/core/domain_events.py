"""Central event-trigger entry point backed by a transactional outbox."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.dashboard.models import NotificationEvent


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
    """
    if dedupe_key is not None:
        existing = await db.execute(
            select(NotificationEvent.id).where(NotificationEvent.dedupe_key == dedupe_key)
        )
        if existing.scalar_one_or_none():
            return None
    item = NotificationEvent(
        event_id=event_id,
        event_type=event_type,
        payload=payload or {},
        dedupe_key=dedupe_key,
    )
    db.add(item)
    await db.flush()
    return item
