"""add score_sheet_templates table

Revision ID: 0001
Revises: (initial)
Create Date: 2026-03-31
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0001"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "score_sheet_templates",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("season_id", sa.String(36), sa.ForeignKey("seasons.id"), nullable=False),
        sa.Column("competition_level_id", sa.String(36), sa.ForeignKey("competition_levels.id"), nullable=True),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column("year", sa.Integer, nullable=False),
        sa.Column("game_theme", sa.String(255)),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("file_url", sa.Text, nullable=False),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("file_size_bytes", sa.Integer),
        sa.Column("raw_text", sa.Text),
        sa.Column("extracted_fields", JSONB),
        sa.Column("confirmed_fields", JSONB),
        sa.Column("ocr_status", sa.String(30), nullable=False, server_default="pending"),
        sa.Column("ocr_error", sa.Text),
        sa.Column("uploaded_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("confirmed_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
    )

    op.create_index(
        "ix_score_sheet_templates_season_id",
        "score_sheet_templates",
        ["season_id"],
    )
    op.create_index(
        "ix_score_sheet_templates_level_id",
        "score_sheet_templates",
        ["competition_level_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_score_sheet_templates_level_id")
    op.drop_index("ix_score_sheet_templates_season_id")
    op.drop_table("score_sheet_templates")
