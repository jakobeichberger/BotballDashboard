"""Double-elimination wiring, per-event bracket weights and outbox hardening

Revision ID: 0024
Revises: 0023
Create Date: 2026-09-24 00:00:00

- scheduled_matches.next_winner_slot / next_loser_slot: the participant
  position a winner or loser takes in the linked match, so advancing through a
  bracket (including the grand final, where position 1 is the winner-bracket
  side) is deterministic.
- event_bracket_weights: bracket weights (A, B, C, …) announced per event.
- notification_events.dedupe_key: reminders queued by periodic tasks are sent
  once; next_attempt_at: backoff between failed delivery attempts.
"""

import sqlalchemy as sa

from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("scheduled_matches", sa.Column("next_winner_slot", sa.Integer(), nullable=True))
    op.add_column("scheduled_matches", sa.Column("next_loser_slot", sa.Integer(), nullable=True))

    op.create_table(
        "event_bracket_weights",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "event_id",
            sa.String(36),
            sa.ForeignKey("events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("category", sa.String(30), nullable=False, server_default="botball"),
        sa.Column("bracket", sa.String(20), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False, server_default="1.0"),
        sa.UniqueConstraint("event_id", "category", "bracket", name="uq_event_bracket_weight"),
    )
    op.create_index("ix_event_bracket_weights_event_id", "event_bracket_weights", ["event_id"])

    op.add_column("notification_events", sa.Column("dedupe_key", sa.String(200), nullable=True))
    op.add_column(
        "notification_events",
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_notification_events_dedupe_key",
        "notification_events",
        ["dedupe_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_notification_events_dedupe_key", table_name="notification_events")
    with op.batch_alter_table("notification_events") as batch:
        batch.drop_column("next_attempt_at")
        batch.drop_column("dedupe_key")

    op.drop_index("ix_event_bracket_weights_event_id", table_name="event_bracket_weights")
    op.drop_table("event_bracket_weights")

    with op.batch_alter_table("scheduled_matches") as batch:
        batch.drop_column("next_loser_slot")
        batch.drop_column("next_winner_slot")
