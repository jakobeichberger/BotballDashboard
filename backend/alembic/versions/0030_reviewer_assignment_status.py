"""Reviewer assignment status check for databases migrated before the 0023 fix

Revision ID: 0030
Revises: 0029

0023 renamed the assignment status "assigned" to "pending", but its first
version kept the check constraint from 0012 (which only allowed "assigned").
0023 is fixed for fresh installs; databases that already ran the old 0023
still reject every new reviewer assignment on PostgreSQL. This re-creates the
constraint with the current vocabulary. It is idempotent: on a database that
ran the fixed 0023 it replaces the constraint with an identical one.
"""

from alembic import op

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None

_STATUSES = "status IN ('pending','in_progress','completed','overdue')"


def upgrade() -> None:
    op.execute("UPDATE reviewer_assignments SET status = 'pending' WHERE status = 'assigned'")
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "ALTER TABLE reviewer_assignments "
            "DROP CONSTRAINT IF EXISTS ck_reviewer_assignment_status"
        )
        op.create_check_constraint(
            "ck_reviewer_assignment_status", "reviewer_assignments", _STATUSES
        )
        return
    with op.batch_alter_table("reviewer_assignments") as batch:
        batch.drop_constraint("ck_reviewer_assignment_status", type_="check")
        batch.create_check_constraint("ck_reviewer_assignment_status", _STATUSES)


def downgrade() -> None:
    # The constraint is the one the fixed 0023 creates; 0023's downgrade
    # restores the old vocabulary. Nothing to undo here.
    pass
