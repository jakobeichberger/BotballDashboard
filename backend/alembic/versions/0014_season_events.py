"""Season events/deadlines table

Revision ID: 0014
Revises: 0013
Create Date: 2026-07-15 00:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "season_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("season_id", sa.String(36), sa.ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("event_type", sa.String(20), nullable=False, server_default="deadline"),
        sa.Column("event_date", sa.Date(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_season_events_season_id", "season_events", ["season_id"])


def downgrade() -> None:
    op.drop_index("ix_season_events_season_id", table_name="season_events")
    op.drop_table("season_events")
