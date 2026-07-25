"""Harden paper/print workflows and active scoring constraints.

Revision ID: 0012
Revises: 0011
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "INSERT INTO permissions (id, name, description) VALUES "
        "(gen_random_uuid()::text, 'papers:write', 'Submit and update team papers'), "
        "(gen_random_uuid()::text, 'dashboard:write', 'Manage announcements')"
    )
    op.execute(
        "INSERT INTO role_permissions (role_id, permission_id) "
        "SELECT r.id, p.id FROM roles r, permissions p "
        "WHERE r.name = 'admin' AND p.name IN ('papers:write', 'dashboard:write')"
    )
    op.execute(
        "INSERT INTO role_permissions (role_id, permission_id) "
        "SELECT r.id, p.id FROM roles r, permissions p "
        "WHERE r.name = 'mentor' AND p.name = 'papers:write'"
    )
    op.create_table(
        "notification_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "event_id",
            sa.String(36),
            sa.ForeignKey("events.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending','delivered','failed')",
            name="ck_notification_event_status",
        ),
    )
    op.create_index("ix_notification_events_event_id", "notification_events", ["event_id"])
    op.create_index("ix_notification_events_event_type", "notification_events", ["event_type"])
    op.create_index("ix_notification_events_status", "notification_events", ["status"])

    op.add_column("printers", sa.Column("device_id", sa.String(100), nullable=True))
    op.create_check_constraint(
        "ck_printer_type",
        "printers",
        "printer_type IN ('octoprint','bambu')",
    )
    op.add_column("print_jobs", sa.Column("progress", sa.Float(), nullable=True))
    op.add_column("print_jobs", sa.Column("status_message", sa.String(500), nullable=True))
    op.add_column("print_jobs", sa.Column("external_job_id", sa.String(255), nullable=True))
    op.add_column(
        "print_jobs", sa.Column("last_polled_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_check_constraint(
        "ck_print_job_status",
        "print_jobs",
        "status IN ('pending','approved','queued','printing','completed','failed','cancelled')",
    )

    op.add_column(
        "reviewer_assignments", sa.Column("due_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "reviewer_assignments",
        sa.Column("status", sa.String(30), nullable=False, server_default="assigned"),
    )
    op.add_column(
        "reviewer_assignments",
        sa.Column("reminder_sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "reviewer_assignments",
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_reviewer_assignment_status",
        "reviewer_assignments",
        "status IN ('assigned','in_progress','completed','overdue')",
    )
    op.create_table(
        "paper_status_history",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "paper_id",
            sa.String(36),
            sa.ForeignKey("papers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("from_status", sa.String(50), nullable=True),
        sa.Column("to_status", sa.String(50), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("changed_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column(
            "changed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_paper_status_history_paper_id", "paper_status_history", ["paper_id"])

    # PostgreSQL treats NULLs as distinct in regular UNIQUE constraints. These
    # expression indexes enforce exactly one active schema/ranking per nullable scope.
    op.execute(
        "WITH duplicates AS ("
        "SELECT id, ROW_NUMBER() OVER ("
        "PARTITION BY season_id, COALESCE(event_id, ''), "
        "COALESCE(competition_level_id, '') ORDER BY version DESC, created_at DESC"
        ") AS row_number FROM scoring_schemas WHERE is_active"
        ") UPDATE scoring_schemas SET is_active = false "
        "WHERE id IN (SELECT id FROM duplicates WHERE row_number > 1)"
    )
    op.execute(
        "WITH duplicates AS ("
        "SELECT id, ROW_NUMBER() OVER ("
        "PARTITION BY event_id, team_id, COALESCE(event_phase_id, ''), "
        "COALESCE(competition_level_id, '') ORDER BY updated_at DESC"
        ") AS row_number FROM rankings"
        ") DELETE FROM rankings "
        "WHERE id IN (SELECT id FROM duplicates WHERE row_number > 1)"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_scoring_schema_one_active_scope "
        "ON scoring_schemas (season_id, COALESCE(event_id, ''), "
        "COALESCE(competition_level_id, '')) WHERE is_active"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_ranking_scope_null_safe "
        "ON rankings (event_id, team_id, COALESCE(event_phase_id, ''), "
        "COALESCE(competition_level_id, ''))"
    )


def downgrade() -> None:
    op.drop_index("uq_ranking_scope_null_safe", table_name="rankings")
    op.drop_index("uq_scoring_schema_one_active_scope", table_name="scoring_schemas")
    op.drop_table("paper_status_history")
    op.drop_constraint("ck_reviewer_assignment_status", "reviewer_assignments", type_="check")
    for column in ("completed_at", "reminder_sent_at", "status", "due_at"):
        op.drop_column("reviewer_assignments", column)
    op.drop_constraint("ck_print_job_status", "print_jobs", type_="check")
    for column in ("last_polled_at", "external_job_id", "status_message", "progress"):
        op.drop_column("print_jobs", column)
    op.drop_column("printers", "device_id")
    op.drop_constraint("ck_printer_type", "printers", type_="check")
    op.drop_table("notification_events")
    op.execute(
        "DELETE FROM role_permissions WHERE permission_id IN "
        "(SELECT id FROM permissions WHERE name IN ('papers:write', 'dashboard:write'))"
    )
    op.execute("DELETE FROM permissions WHERE name IN ('papers:write', 'dashboard:write')")
