"""Printing workflow: file uploads, rejection, live status, filament spools

Revision ID: 0022
Revises: 0021
Create Date: 2026-09-24 00:00:00

- print_jobs gets the uploaded file's path/size, live adapter data
  (remaining time, error), the rejection reason, the quota-override flag and
  the filament spool the job was printed with.
- 'rejected' becomes a valid job status.
- 'generic' becomes a valid printer type: a manually operated printer that
  has no adapter and is never polled (the UI already offered it).
- printers remember the last adapter state for the read-only status view.

Constraint changes go through batch_alter_table so they also work on SQLite.
"""

import sqlalchemy as sa

from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None

_OLD_JOB_STATUSES = "'pending','approved','queued','printing','completed','failed','cancelled'"
_NEW_JOB_STATUSES = _OLD_JOB_STATUSES + ",'rejected'"


def upgrade() -> None:
    with op.batch_alter_table("printers") as batch:
        batch.add_column(sa.Column("current_state", sa.String(30), nullable=True))
        batch.add_column(sa.Column("status_message", sa.String(500), nullable=True))
        batch.drop_constraint("ck_printer_type", type_="check")
        batch.create_check_constraint(
            "ck_printer_type", "printer_type IN ('octoprint','bambu','generic')"
        )

    with op.batch_alter_table("print_jobs") as batch:
        batch.add_column(sa.Column("file_path", sa.Text(), nullable=True))
        batch.add_column(sa.Column("file_size_bytes", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("remaining_seconds", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("error_message", sa.Text(), nullable=True))
        batch.add_column(sa.Column("rejection_reason", sa.Text(), nullable=True))
        batch.add_column(
            sa.Column("quota_override", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch.add_column(sa.Column("spool_id", sa.String(36), nullable=True))
        batch.create_foreign_key(
            "fk_print_jobs_spool_id",
            "filament_spools",
            ["spool_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.drop_constraint("ck_print_job_status", type_="check")
        batch.create_check_constraint("ck_print_job_status", f"status IN ({_NEW_JOB_STATUSES})")


def downgrade() -> None:
    # Values the old constraints do not allow: a rejected job is closest to a
    # cancelled one, a generic printer becomes an inactive OctoPrint entry.
    op.execute("UPDATE print_jobs SET status = 'cancelled' WHERE status = 'rejected'")
    op.execute(
        "UPDATE printers SET printer_type = 'octoprint', is_active = false "
        "WHERE printer_type = 'generic'"
    )

    with op.batch_alter_table("print_jobs") as batch:
        batch.drop_constraint("ck_print_job_status", type_="check")
        batch.create_check_constraint("ck_print_job_status", f"status IN ({_OLD_JOB_STATUSES})")
        batch.drop_constraint("fk_print_jobs_spool_id", type_="foreignkey")
        for column in (
            "spool_id",
            "quota_override",
            "rejection_reason",
            "error_message",
            "remaining_seconds",
            "file_size_bytes",
            "file_path",
        ):
            batch.drop_column(column)

    with op.batch_alter_table("printers") as batch:
        batch.drop_constraint("ck_printer_type", type_="check")
        batch.create_check_constraint("ck_printer_type", "printer_type IN ('octoprint','bambu')")
        batch.drop_column("status_message")
        batch.drop_column("current_state")
