"""3D Printing module: printers, print_jobs, quotas, filament_spools

Revision ID: 0007
Revises: 0006
Create Date: 2026-01-01 00:05:00
"""
from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "printers",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("model", sa.String(255), nullable=True),
        sa.Column("printer_type", sa.String(50), nullable=False, server_default="bambu"),
        sa.Column("api_url", sa.Text, nullable=True),
        sa.Column("api_key_encrypted", sa.Text, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("is_online", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "print_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("printer_id", sa.String(36), sa.ForeignKey("printers.id", ondelete="SET NULL"), nullable=True),
        sa.Column("team_id", sa.String(36), sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False),
        sa.Column("season_id", sa.String(36), sa.ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("submitted_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("file_url", sa.Text, nullable=True),
        sa.Column("material", sa.String(50), nullable=False, server_default="PLA"),
        sa.Column("color", sa.String(100), nullable=True),
        sa.Column("estimated_grams", sa.Float, nullable=True),
        sa.Column("actual_grams", sa.Float, nullable=True),
        sa.Column("estimated_minutes", sa.Integer, nullable=True),
        sa.Column("actual_minutes", sa.Integer, nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("priority", sa.Integer, nullable=False, server_default="0"),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("approved_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_print_jobs_team_id", "print_jobs", ["team_id"])
    op.create_index("ix_print_jobs_season_id", "print_jobs", ["season_id"])

    op.create_table(
        "team_season_print_quotas",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("team_id", sa.String(36), sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False),
        sa.Column("season_id", sa.String(36), sa.ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("max_parts", sa.Integer, nullable=False, server_default="4"),
        sa.Column("soft_limit_parts", sa.Integer, nullable=False, server_default="3"),
        sa.Column("max_grams", sa.Float, nullable=True),
        sa.Column("used_parts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("used_grams", sa.Float, nullable=False, server_default="0"),
        sa.Column("notes", sa.Text, nullable=True),
    )
    op.create_index("ix_print_quotas_team_season", "team_season_print_quotas", ["team_id", "season_id"])

    op.create_table(
        "filament_spools",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("printer_id", sa.String(36), sa.ForeignKey("printers.id", ondelete="SET NULL"), nullable=True),
        sa.Column("material", sa.String(50), nullable=False, server_default="PLA"),
        sa.Column("color", sa.String(100), nullable=True),
        sa.Column("brand", sa.String(100), nullable=True),
        sa.Column("initial_grams", sa.Float, nullable=False, server_default="1000"),
        sa.Column("remaining_grams", sa.Float, nullable=False, server_default="1000"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("filament_spools")
    op.drop_table("team_season_print_quotas")
    op.drop_table("print_jobs")
    op.drop_table("printers")
