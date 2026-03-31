"""Teams module: teams, team_members, team_season_registrations

Revision ID: 0004
Revises: 0003
Create Date: 2026-01-01 00:02:00
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "teams",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("team_number", sa.String(50), nullable=True),
        sa.Column("school", sa.String(255), nullable=True),
        sa.Column("city", sa.String(255), nullable=True),
        sa.Column("country", sa.String(100), nullable=False, server_default="DE"),
        sa.Column("competition_level_id", sa.String(36), sa.ForeignKey("competition_levels.id"), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_teams_team_number", "teams", ["team_number"])

    op.create_table(
        "team_members",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("team_id", sa.String(36), sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("role", sa.String(50), nullable=False, server_default="member"),
    )
    op.create_index("ix_team_members_team_id", "team_members", ["team_id"])

    op.create_table(
        "team_season_registrations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("team_id", sa.String(36), sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False),
        sa.Column("season_id", sa.String(36), sa.ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("competition_level_id", sa.String(36), sa.ForeignKey("competition_levels.id"), nullable=True),
        sa.Column("registered_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("confirmed", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("notes", sa.Text, nullable=True),
    )
    op.create_index("ix_team_season_registrations_team_id", "team_season_registrations", ["team_id"])
    op.create_index("ix_team_season_registrations_season_id", "team_season_registrations", ["season_id"])


def downgrade() -> None:
    op.drop_table("team_season_registrations")
    op.drop_table("team_members")
    op.drop_table("teams")
