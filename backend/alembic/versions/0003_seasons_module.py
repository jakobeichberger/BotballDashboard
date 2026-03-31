"""Seasons module: seasons, season_phases, competition_levels

Revision ID: 0003
Revises: 0002
Create Date: 2026-01-01 00:01:00
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "seasons",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("year", sa.Integer, nullable=False),
        sa.Column("game_theme", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("registration_open", sa.Date, nullable=True),
        sa.Column("registration_close", sa.Date, nullable=True),
        sa.Column("event_start", sa.Date, nullable=True),
        sa.Column("event_end", sa.Date, nullable=True),
        sa.Column("paper_submission_deadline", sa.Date, nullable=True),
        sa.Column("print_submission_deadline", sa.Date, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "season_phases",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("season_id", sa.String(36), sa.ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("phase_type", sa.String(50), nullable=False),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("rounds", sa.Integer, nullable=False, server_default="3"),
        sa.Column("start_date", sa.Date, nullable=True),
        sa.Column("end_date", sa.Date, nullable=True),
    )
    op.create_index("ix_season_phases_season_id", "season_phases", ["season_id"])

    op.create_table(
        "competition_levels",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("code", sa.String(20), nullable=False, unique=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
    )

    # Seed competition levels
    op.execute("""
        INSERT INTO competition_levels (id, name, code, description) VALUES
        (gen_random_uuid()::text, 'ECER', 'ECER', 'Elementary Competition Event Robotics'),
        (gen_random_uuid()::text, 'GCER', 'GCER', 'General Competition Event Robotics'),
        (gen_random_uuid()::text, 'Junior', 'JR', 'Junior division')
    """)


def downgrade() -> None:
    op.drop_table("season_phases")
    op.drop_table("seasons")
    op.drop_table("competition_levels")
