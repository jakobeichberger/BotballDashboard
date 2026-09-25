"""Notification preferences, notification-center read state, module switches

Revision ID: 0027
Revises: 0026
Create Date: 2026-09-24 00:00:00

* users.notification_preferences: per-category push opt-outs.
* notification_reads: which outbox notifications a user has read in the
  in-app notification center.
* events.active_modules: paper review, 3D printing and the robot gallery are
  now per-event modules. They were always available before, so every existing
  event gets them switched on — upgrading must not hide existing data.
"""

import json

import sqlalchemy as sa

from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None

_ALWAYS_ON_BEFORE = ("paper", "printing", "bots")


def _load(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = json.loads(value)
    return list(value)


def _rewrite_modules(transform) -> None:
    bind = op.get_bind()
    events = sa.table("events", sa.column("id", sa.String), sa.column("active_modules", sa.JSON))
    for row in bind.execute(sa.select(events.c.id, events.c.active_modules)).all():
        modules = transform(_load(row.active_modules))
        bind.execute(events.update().where(events.c.id == row.id).values(active_modules=modules))


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("notification_preferences", sa.JSON(), nullable=False, server_default="{}"),
    )
    op.create_table(
        "notification_reads",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "notification_id",
            sa.String(36),
            sa.ForeignKey("notification_events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "read_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("user_id", "notification_id", name="uq_notification_read_user_item"),
    )
    op.create_index("ix_notification_reads_user_id", "notification_reads", ["user_id"])
    op.create_index(
        "ix_notification_reads_notification_id", "notification_reads", ["notification_id"]
    )
    _rewrite_modules(lambda modules: modules + [m for m in _ALWAYS_ON_BEFORE if m not in modules])


def downgrade() -> None:
    # Before this revision only the competition modules were stored.
    _rewrite_modules(
        lambda modules: [m for m in modules if m not in ("printing", "bots")] or ["seeding"]
    )
    op.drop_index("ix_notification_reads_notification_id", table_name="notification_reads")
    op.drop_index("ix_notification_reads_user_id", table_name="notification_reads")
    op.drop_table("notification_reads")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("notification_preferences")
