"""Performance: notification recipient index, outbox claim state, missing indexes

Revision ID: 0032
Revises: 0031

- notification_recipients: who each outbox notification is addressed to
  (NULL user = broadcast), indexed by (user_id, created_at). The notification
  center reads a user's notifications through it instead of scanning the
  newest 500 outbox rows and filtering their JSON payloads in Python.
  Existing outbox rows are backfilled from their payloads.
- notification_events.status gains 'sending': the worker claims a batch,
  commits, and sends without holding row locks (lease in next_attempt_at).
- Indexes for frequent lookups: matches(scheduled_match_id),
  matches(event_id, team_id), team_members(user_id),
  notification_events(created_at) plus a partial index over the open outbox
  rows (next_attempt_at WHERE status IN ('pending','sending')),
  scheduled_matches(status, scheduled_at), score_revisions(event_id, created_at).
"""

import json
import uuid

import sqlalchemy as sa

from alembic import op

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None

_OPEN_OUTBOX = "status IN ('pending', 'sending')"
_STATUSES_NEW = "status IN ('pending','sending','delivered','failed')"
_STATUSES_OLD = "status IN ('pending','delivered','failed')"

_INDEXES = (
    ("ix_matches_scheduled_match_id", "matches", ["scheduled_match_id"]),
    ("ix_matches_event_team", "matches", ["event_id", "team_id"]),
    ("ix_team_members_user_id", "team_members", ["user_id"]),
    ("ix_notification_events_created_at", "notification_events", ["created_at"]),
    ("ix_scheduled_matches_status_scheduled_at", "scheduled_matches", ["status", "scheduled_at"]),
    ("ix_score_revisions_event_created", "score_revisions", ["event_id", "created_at"]),
)


def _replace_status_check(statuses: str) -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            "ALTER TABLE notification_events DROP CONSTRAINT IF EXISTS ck_notification_event_status"
        )
        op.create_check_constraint("ck_notification_event_status", "notification_events", statuses)
        return
    existing = {c["name"] for c in sa.inspect(bind).get_check_constraints("notification_events")}
    with op.batch_alter_table("notification_events") as batch:
        if "ck_notification_event_status" in existing:
            batch.drop_constraint("ck_notification_event_status", type_="check")
        batch.create_check_constraint("ck_notification_event_status", statuses)


def _payload(value) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str | bytes):
        try:
            parsed = json.loads(value)
        except ValueError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _backfill_recipients() -> None:
    bind = op.get_bind()
    users = {row[0] for row in bind.execute(sa.text("SELECT id FROM users"))}
    # Untyped columns: created_at is copied back exactly as the driver
    # returned it (a datetime on PostgreSQL, text on SQLite).
    recipients = sa.table(
        "notification_recipients",
        sa.column("id"),
        sa.column("notification_id"),
        sa.column("user_id"),
        sa.column("created_at"),
    )
    rows = []
    for notification_id, payload, created_at in bind.execute(
        sa.text("SELECT id, payload, created_at FROM notification_events")
    ):
        data = _payload(payload)
        if data.get("broadcast"):
            addressed: list[str | None] = [None]
        else:
            wanted = set(data.get("userIds") or [])
            if data.get("userId"):
                wanted.add(data["userId"])
            addressed = sorted(u for u in wanted if u in users)
        rows.extend(
            {
                "id": str(uuid.uuid4()),
                "notification_id": notification_id,
                "user_id": user_id,
                "created_at": created_at,
            }
            for user_id in addressed
        )
        if len(rows) >= 1000:
            op.bulk_insert(recipients, rows)
            rows = []
    if rows:
        op.bulk_insert(recipients, rows)


def upgrade() -> None:
    op.create_table(
        "notification_recipients",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "notification_id",
            sa.String(36),
            sa.ForeignKey("notification_events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_notification_recipients_notification_id",
        "notification_recipients",
        ["notification_id"],
    )
    op.create_index(
        "ix_notification_recipients_user_created",
        "notification_recipients",
        ["user_id", "created_at"],
    )
    _backfill_recipients()

    _replace_status_check(_STATUSES_NEW)

    for name, table, columns in _INDEXES:
        op.create_index(name, table, columns)
    op.create_index(
        "ix_notification_events_due",
        "notification_events",
        ["next_attempt_at"],
        postgresql_where=sa.text(_OPEN_OUTBOX),
        sqlite_where=sa.text(_OPEN_OUTBOX),
    )


def downgrade() -> None:
    op.drop_index("ix_notification_events_due", table_name="notification_events")
    for name, table, _columns in reversed(_INDEXES):
        op.drop_index(name, table_name=table)

    # Rows claimed by a worker go back to the queue.
    op.execute("UPDATE notification_events SET status = 'pending' WHERE status = 'sending'")
    _replace_status_check(_STATUSES_OLD)

    op.drop_index("ix_notification_recipients_user_created", table_name="notification_recipients")
    op.drop_index(
        "ix_notification_recipients_notification_id", table_name="notification_recipients"
    )
    op.drop_table("notification_recipients")
