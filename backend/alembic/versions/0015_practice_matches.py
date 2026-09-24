"""Add is_practice flag to matches (preparation/practice runs)

Revision ID: 0015
Revises: 0014
Create Date: 2026-07-15 00:00:00

Practice runs let teams track their preparation points separately; they are
excluded from the official contest ranking.
"""

import sqlalchemy as sa

from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "matches",
        sa.Column("is_practice", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("matches", "is_practice")
