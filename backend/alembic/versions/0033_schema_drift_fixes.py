"""Schema drift: bring the migrated schema in line with the models

Revision ID: 0033
Revises: 0032

`alembic check` against a database migrated to 0032 reported differences
between the migrations and the models. Most were model declarations that
lagged behind the migrated schema (JSONB columns, partial/expression unique
indexes, index names) and are fixed in the models. What remains are the
places where the database was looser or slower than the application assumes:

- print_jobs(printer_id) gets its index. The printer queue queries jobs by
  printer, and deleting a printer (ON DELETE SET NULL) had to scan the table.
- event_registrations.team_id becomes NOT NULL. 0010 created it nullable, but
  a registration always belongs to a team (the unique constraint on
  (event_id, team_id) cannot even keep team-less rows apart). Rows without a
  team cannot be created by the application; any left over are removed.
- score_sheet_templates.uploaded_at becomes NOT NULL (0001 left it nullable
  next to its server default); missing values are backfilled with now.
"""

import sqlalchemy as sa

from alembic import op

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_print_jobs_printer_id", "print_jobs", ["printer_id"])

    op.execute("DELETE FROM event_registrations WHERE team_id IS NULL")
    with op.batch_alter_table("event_registrations") as batch:
        batch.alter_column("team_id", existing_type=sa.String(36), nullable=False)

    op.execute(
        "UPDATE score_sheet_templates SET uploaded_at = CURRENT_TIMESTAMP WHERE uploaded_at IS NULL"
    )
    with op.batch_alter_table("score_sheet_templates") as batch:
        batch.alter_column(
            "uploaded_at",
            existing_type=sa.DateTime(timezone=True),
            existing_server_default=sa.func.now(),
            nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("score_sheet_templates") as batch:
        batch.alter_column(
            "uploaded_at",
            existing_type=sa.DateTime(timezone=True),
            existing_server_default=sa.func.now(),
            nullable=True,
        )
    with op.batch_alter_table("event_registrations") as batch:
        batch.alter_column("team_id", existing_type=sa.String(36), nullable=True)
    op.drop_index("ix_print_jobs_printer_id", table_name="print_jobs")
