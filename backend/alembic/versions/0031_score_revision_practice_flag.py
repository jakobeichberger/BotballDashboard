"""Practice flag on score revisions

Revision ID: 0031
Revises: 0030

Practice runs are only visible to the team itself and to organizers; their
score history must not leak through the event audit trail either. The history
outlives the match (a deleted match keeps its revisions), so the revision rows
carry their own copy of Match.is_practice.

Rows of matches that still exist are backfilled from the match. Rows of
matches deleted before this migration keep NULL ("unknown"); the audit trail
treats them like practice runs and shows them only to the team and organizers.
"""

import sqlalchemy as sa

from alembic import op

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("score_revisions") as batch:
        batch.add_column(sa.Column("is_practice", sa.Boolean(), nullable=True))
    op.execute(
        "UPDATE score_revisions SET is_practice = ("
        "SELECT matches.is_practice FROM matches WHERE matches.id = score_revisions.match_ref)"
    )


def downgrade() -> None:
    with op.batch_alter_table("score_revisions") as batch:
        batch.drop_column("is_practice")
