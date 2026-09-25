import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class Announcement(Base):
    __tablename__ = "announcements"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    season_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("seasons.id", ondelete="CASCADE"), nullable=True, index=True
    )
    event_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("events.id", ondelete="CASCADE"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    audience: Mapped[str] = mapped_column(String(50), default="all", nullable=False)
    # all | teams | reviewers | jurors | internal
    is_published: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


#: Outbox rows the worker still has to deliver ("sending" = claimed, see
#: modules.dashboard.tasks.deliver_pending). The partial index over them stays
#: small however much delivered history the table holds.
OPEN_OUTBOX_STATUSES = ("pending", "sending")
_OPEN_OUTBOX = text("status IN ('pending', 'sending')")


class NotificationEvent(Base):
    """Transactional outbox consumed by the notification worker.

    status: pending → sending (claimed by a worker, leased until
    next_attempt_at) → delivered | pending (retry) | failed.
    """

    __tablename__ = "notification_events"
    __table_args__ = (
        Index(
            "ix_notification_events_due",
            "next_attempt_at",
            postgresql_where=_OPEN_OUTBOX,
            sqlite_where=_OPEN_OUTBOX,
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    event_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("events.id", ondelete="CASCADE"), nullable=True, index=True
    )
    event_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    # Optional idempotency key: reminders ("match starts soon", deadlines) are
    # queued by periodic tasks and must reach each recipient only once.
    dedupe_key: Mapped[str | None] = mapped_column(
        String(200), nullable=True, unique=True, index=True
    )
    # Earliest time of the next delivery attempt after a failed one (backoff);
    # while "sending", the end of the claiming worker's lease.
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class NotificationRecipient(Base):
    """Who an outbox notification is addressed to (the notification center's index).

    One row per addressed user, written with the outbox row (core.domain_events);
    a broadcast has a single row with ``user_id`` NULL, meaning "every user".
    The center reads a user's notifications through the (user_id, created_at)
    index instead of scanning the newest outbox rows and filtering their JSON
    payloads in Python. ``created_at`` repeats the notification's time for that
    index.
    """

    __tablename__ = "notification_recipients"
    __table_args__ = (Index("ix_notification_recipients_user_created", "user_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    notification_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("notification_events.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CalendarFeedToken(Base):
    """A per-user secret for subscribing to the deadline iCal feed.

    Calendar apps cannot send a bearer token, so the feed URL carries its own
    credential. Only a SHA-256 hash is stored: the plain token is shown once
    when it is created, and rotating or revoking it invalidates every URL that
    was handed out before. The token grants nothing but the read-only feed.
    """

    __tablename__ = "calendar_feed_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class NotificationRead(Base):
    """Read receipt of one outbox notification for one user (notification center)."""

    __tablename__ = "notification_reads"
    __table_args__ = (
        UniqueConstraint("user_id", "notification_id", name="uq_notification_read_user_item"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    notification_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("notification_events.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    read_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
