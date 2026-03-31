"""Scoring module: scoring_schemas, matches, rankings

Revision ID: 0005
Revises: 0004
Create Date: 2026-01-01 00:03:00
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scoring_schemas",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("season_id", sa.String(36), sa.ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("competition_level_id", sa.String(36), sa.ForeignKey("competition_levels.id"), nullable=True),
        sa.Column("fields", JSONB, nullable=False, server_default="[]"),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_scoring_schemas_season_id", "scoring_schemas", ["season_id"])

    op.create_table(
        "matches",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("season_id", sa.String(36), sa.ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("phase_id", sa.String(36), sa.ForeignKey("season_phases.id", ondelete="SET NULL"), nullable=True),
        sa.Column("team_id", sa.String(36), sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False),
        sa.Column("competition_level_id", sa.String(36), sa.ForeignKey("competition_levels.id"), nullable=True),
        sa.Column("round_number", sa.Integer, nullable=False, server_default="1"),
        sa.Column("table_number", sa.Integer, nullable=True),
        sa.Column("raw_scores", JSONB, nullable=False, server_default="{}"),
        sa.Column("total_score", sa.Float, nullable=False, server_default="0"),
        sa.Column("is_disqualified", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("yellow_card", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("red_card", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("entered_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("confirmed_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_matches_season_id", "matches", ["season_id"])
    op.create_index("ix_matches_team_id", "matches", ["team_id"])
    op.create_index("ix_matches_phase_id", "matches", ["phase_id"])

    op.create_table(
        "rankings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("season_id", sa.String(36), sa.ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("phase_id", sa.String(36), sa.ForeignKey("season_phases.id"), nullable=True),
        sa.Column("competition_level_id", sa.String(36), sa.ForeignKey("competition_levels.id"), nullable=True),
        sa.Column("team_id", sa.String(36), sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rank", sa.Integer, nullable=False),
        sa.Column("seed_score", sa.Float, nullable=False, server_default="0"),
        sa.Column("best_score", sa.Float, nullable=False, server_default="0"),
        sa.Column("average_score", sa.Float, nullable=False, server_default="0"),
        sa.Column("rounds_played", sa.Integer, nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_rankings_season_id", "rankings", ["season_id"])


def downgrade() -> None:
    op.drop_table("rankings")
    op.drop_table("matches")
    op.drop_table("scoring_schemas")
