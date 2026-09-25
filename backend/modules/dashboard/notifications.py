"""Notification categories, per-user preferences and the in-app notification
center, all read from the transactional outbox (``notification_events``) and
its recipient index (``notification_recipients``).

Every outbox event maps to one user-facing category. Users can switch push
delivery off per category (``User.notification_preferences``); the in-app
center still lists everything addressed to them, it is the fallback channel
when push is unavailable or muted.
"""

from datetime import UTC, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.mail_templates import render_notification
from modules.dashboard.models import NotificationEvent, NotificationRead, NotificationRecipient

CATEGORIES: tuple[str, ...] = (
    "match_soon",
    "score_corrected",
    "deadlines",
    "paper_status",
    "print_status",
    "announcements",
)

# Outbox event types (current and planned producers) → category. Producers may
# also set payload["category"] explicitly.
EVENT_CATEGORIES: dict[str, str] = {
    "match_soon": "match_soon",
    "match_starting_soon": "match_soon",
    "match_called": "match_soon",
    "schedule_updated": "match_soon",
    "score_corrected": "score_corrected",
    "match_corrected": "score_corrected",
    "deadline_reminder": "deadlines",
    "paper_deadline_reminder": "deadlines",
    "review_reminder": "deadlines",
    "paper_status_changed": "paper_status",
    "reviewer_assigned": "paper_status",
    "print_status_changed": "print_status",
    "announcement_published": "announcements",
}


def category_of(event_type: str, payload: dict | None = None) -> str | None:
    explicit = (payload or {}).get("category")
    if explicit in CATEGORIES:
        return str(explicit)
    return EVENT_CATEGORIES.get(event_type)


def normalize_preferences(stored: dict | None) -> dict[str, bool]:
    """All categories with their effective value; unset ones default to on."""
    stored = stored or {}
    return {category: bool(stored.get(category, True)) for category in CATEGORIES}


def wants_push(preferences: dict | None, category: str | None) -> bool:
    # Events without a category (internal/system) are not muted by preferences.
    if category is None:
        return True
    return normalize_preferences(preferences)[category]


def recipients_of(payload: dict) -> set[str]:
    """Users a notification is addressed to: ``userIds`` and ``userId``.

    Together with ``broadcast`` (everyone) this is the recipient rule of push
    delivery and of the notification center, which stores its outcome per
    outbox row in notification_recipients (see core.domain_events).
    """
    user_ids = set(payload.get("userIds") or [])
    if payload.get("userId"):
        user_ids.add(payload["userId"])
    return user_ids


def _title(item: NotificationEvent, language: str | None = None) -> str:
    message = render_notification(item.payload, language)
    if message:
        return message.subject
    return item.payload.get("title") or item.event_type.replace("_", " ").title()


def _body(item: NotificationEvent, language: str | None = None) -> str:
    message = render_notification(item.payload, language)
    if message:
        return message.summary
    return item.payload.get("message") or item.payload.get("body") or ""


def _addressed_to(user_id: str):
    """Recipient rows addressed to the user: explicitly, or as a broadcast."""
    return or_(NotificationRecipient.user_id == user_id, NotificationRecipient.user_id.is_(None))


def _unread_by(user_id: str):
    return ~(
        select(NotificationRead.id)
        .where(
            NotificationRead.user_id == user_id,
            NotificationRead.notification_id == NotificationRecipient.notification_id,
        )
        .exists()
    )


async def list_for_user(
    db: AsyncSession,
    user_id: str,
    *,
    limit: int = 30,
    unread_only: bool = False,
    language: str | None = None,
) -> tuple[list[dict], int]:
    """Recent notifications addressed to `user_id` and the unread count.

    Read through notification_recipients and its (user_id, created_at)
    index: only the user's own rows are touched, however large the outbox
    is. Templated notifications are rendered in `language` (the user's
    profile language); others keep the text they were queued with.
    """
    query = (
        select(NotificationEvent, NotificationRecipient.created_at)
        .join(NotificationRecipient, NotificationRecipient.notification_id == NotificationEvent.id)
        .where(_addressed_to(user_id))
        .order_by(NotificationRecipient.created_at.desc(), NotificationEvent.id)
        .limit(limit)
    )
    if unread_only:
        query = query.where(_unread_by(user_id))
    rows = [row for row, _created in await db.execute(query)]
    read_ids: set[str] = set()
    if rows and not unread_only:
        read_ids = set(
            (
                await db.execute(
                    select(NotificationRead.notification_id).where(
                        NotificationRead.user_id == user_id,
                        NotificationRead.notification_id.in_([row.id for row in rows]),
                    )
                )
            ).scalars()
        )
    unread = (
        await db.execute(
            select(func.count(func.distinct(NotificationRecipient.notification_id))).where(
                _addressed_to(user_id), _unread_by(user_id)
            )
        )
    ).scalar_one()
    items = [
        {
            "id": row.id,
            "event_id": row.event_id,
            "event_type": row.event_type,
            "category": category_of(row.event_type, row.payload),
            "title": _title(row, language),
            "body": _body(row, language),
            "url": row.payload.get("url"),
            "created_at": row.created_at,
            "read": row.id in read_ids,
        }
        for row in rows
    ]
    return items, int(unread)


async def mark_read(db: AsyncSession, user_id: str, notification_ids: list[str]) -> int:
    """Mark the given notifications (addressed to the user) as read."""
    if not notification_ids:
        return 0
    targets = set(
        (
            await db.execute(
                select(NotificationRecipient.notification_id).where(
                    NotificationRecipient.notification_id.in_(notification_ids),
                    _addressed_to(user_id),
                )
            )
        ).scalars()
    )
    return await _add_reads(db, user_id, targets)


async def mark_all_read(db: AsyncSession, user_id: str) -> int:
    targets = set(
        (
            await db.execute(
                select(NotificationRecipient.notification_id).where(
                    _addressed_to(user_id), _unread_by(user_id)
                )
            )
        ).scalars()
    )
    return await _add_reads(db, user_id, targets)


async def _add_reads(db: AsyncSession, user_id: str, targets: set[str]) -> int:
    if not targets:
        return 0
    already = set(
        (
            await db.execute(
                select(NotificationRead.notification_id).where(
                    NotificationRead.user_id == user_id,
                    NotificationRead.notification_id.in_(targets),
                )
            )
        ).scalars()
    )
    now = datetime.now(UTC)
    for notification_id in targets - already:
        db.add(NotificationRead(user_id=user_id, notification_id=notification_id, read_at=now))
    await db.flush()
    return len(targets - already)
