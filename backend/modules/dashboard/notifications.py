"""Notification categories, per-user preferences and the in-app notification
center, all read from the transactional outbox (``notification_events``).

Every outbox event maps to one user-facing category. Users can switch push
delivery off per category (``User.notification_preferences``); the in-app
center still lists everything addressed to them, it is the fallback channel
when push is unavailable or muted.
"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.mail_templates import render_notification
from modules.dashboard.models import NotificationEvent, NotificationRead

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

# How far back the notification center looks; older outbox rows are history.
CENTER_SCAN_LIMIT = 500


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
    user_ids = set(payload.get("userIds") or [])
    if payload.get("userId"):
        user_ids.add(payload["userId"])
    return user_ids


def is_addressed_to(payload: dict, user_id: str) -> bool:
    """Same recipient rule as push delivery: explicit users or a broadcast."""
    return bool(payload.get("broadcast")) or user_id in recipients_of(payload)


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


async def list_for_user(
    db: AsyncSession,
    user_id: str,
    *,
    limit: int = 30,
    unread_only: bool = False,
    language: str | None = None,
) -> tuple[list[dict], int]:
    """Recent notifications addressed to `user_id` and the unread count.

    Templated notifications are rendered in `language` (the user's profile
    language); others keep the text they were queued with.
    """
    rows = list(
        (
            await db.execute(
                select(NotificationEvent)
                .order_by(NotificationEvent.created_at.desc())
                .limit(CENTER_SCAN_LIMIT)
            )
        ).scalars()
    )
    mine = [row for row in rows if is_addressed_to(row.payload or {}, user_id)]
    read_ids = set(
        (
            await db.execute(
                select(NotificationRead.notification_id).where(
                    NotificationRead.user_id == user_id,
                    NotificationRead.notification_id.in_([row.id for row in mine]),
                )
            )
        ).scalars()
    )
    unread = sum(1 for row in mine if row.id not in read_ids)
    items = []
    for row in mine:
        is_read = row.id in read_ids
        if unread_only and is_read:
            continue
        items.append(
            {
                "id": row.id,
                "event_id": row.event_id,
                "event_type": row.event_type,
                "category": category_of(row.event_type, row.payload),
                "title": _title(row, language),
                "body": _body(row, language),
                "url": row.payload.get("url"),
                "created_at": row.created_at,
                "read": is_read,
            }
        )
        if len(items) >= limit:
            break
    return items, unread


async def mark_read(db: AsyncSession, user_id: str, notification_ids: list[str]) -> int:
    """Mark the given notifications (addressed to the user) as read."""
    if not notification_ids:
        return 0
    rows = list(
        (
            await db.execute(
                select(NotificationEvent).where(NotificationEvent.id.in_(notification_ids))
            )
        ).scalars()
    )
    targets = {row.id for row in rows if is_addressed_to(row.payload or {}, user_id)}
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


async def mark_all_read(db: AsyncSession, user_id: str) -> int:
    items, _unread = await list_for_user(db, user_id, limit=CENTER_SCAN_LIMIT, unread_only=True)
    return await mark_read(db, user_id, [item["id"] for item in items])
