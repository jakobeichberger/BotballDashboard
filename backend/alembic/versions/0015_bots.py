"""Bot gallery: bots table

Revision ID: 0015
Revises: 0014
Create Date: 2026-07-16 00:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("team_id", sa.String(36), sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=True),
        sa.Column("external_team_name", sa.String(255), nullable=True),
        sa.Column("season_id", sa.String(36), sa.ForeignKey("seasons.id", ondelete="SET NULL"), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("functionality", sa.Text(), nullable=True),
        sa.Column("drive_type", sa.String(100), nullable=True),
        sa.Column("sensors", sa.Text(), nullable=True),
        sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("image_name", sa.String(255), nullable=True),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_bots_team_id", "bots", ["team_id"])
    op.create_index("ix_bots_season_id", "bots", ["season_id"])


def downgrade() -> None:
    op.drop_index("ix_bots_season_id", table_name="bots")
    op.drop_index("ix_bots_team_id", table_name="bots")
    op.drop_table("bots")
