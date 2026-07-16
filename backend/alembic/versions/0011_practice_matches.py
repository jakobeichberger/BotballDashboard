"""Add is_practice flag to matches (preparation/practice runs)

Revision ID: 0011
Revises: 0010
Create Date: 2026-07-15 00:00:00

Practice runs let teams track their preparation points separately; they are
excluded from the official contest ranking.
"""
from alembic import op
import sqlalchemy as sa

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "matches",
        sa.Column("is_practice", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("matches", "is_practice")
