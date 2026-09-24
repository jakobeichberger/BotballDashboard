"""Calendar feed tokens for the per-user deadline iCal subscription

Revision ID: 0026
Revises: 0025
Create Date: 2026-09-24 00:00:00

Calendar apps poll a feed URL without an Authorization header, so each user
gets a revocable secret for GET /api/dashboard/deadlines.ics. Only the SHA-256
hash of the token is stored.
"""

import sqlalchemy as sa

from alembic import op

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "calendar_feed_tokens",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("user_id", name="uq_calendar_feed_tokens_user_id"),
        sa.UniqueConstraint("token_hash", name="uq_calendar_feed_tokens_token_hash"),
    )


def downgrade() -> None:
    op.drop_table("calendar_feed_tokens")
