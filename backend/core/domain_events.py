"""Central event-trigger entry point backed by a transactional outbox."""

from sqlalchemy.ext.asyncio import AsyncSession

from modules.dashboard.models import NotificationEvent


async def emit_event(
    db: AsyncSession,
    event_type: str,
    *,
    event_id: str | None = None,
    payload: dict | None = None,
) -> NotificationEvent:
    item = NotificationEvent(
        event_id=event_id,
        event_type=event_type,
        payload=payload or {},
    )
    db.add(item)
    await db.flush()
    return item
