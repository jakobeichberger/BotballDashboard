"""Season lifecycle, access-token revocation and password reset

Revision ID: 0021
Revises: 0020
Create Date: 2026-09-24 00:00:00

- seasons.status (draft | active | finished | archived). Archived seasons are
  read-only; drafts are hidden from users without seasons:write. Existing rows
  are backfilled from is_active: the active season becomes "active", every
  other one "finished" (so nothing that was visible before disappears).
- users.token_version: embedded in every access token and bumped on password
  change/reset, deactivation and account deletion, so access tokens issued
  before that are rejected instead of living out their 15 minutes.
- users.anonymized_at: set when an account is deleted (DSGVO). The row stays so
  foreign keys in the history (scores entered, reviews, …) remain valid.
- password_reset_tokens: single-use, hashed, one-hour reset tokens.
"""

import sqlalchemy as sa

from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "seasons",
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
    )
    op.execute("UPDATE seasons SET status = CASE WHEN is_active THEN 'active' ELSE 'finished' END")
    op.create_index("ix_seasons_status", "seasons", ["status"])

    op.add_column(
        "users",
        sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "users",
        sa.Column("anonymized_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "password_reset_tokens",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(255), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_password_reset_tokens_user_id", "password_reset_tokens", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_password_reset_tokens_user_id", table_name="password_reset_tokens")
    op.drop_table("password_reset_tokens")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("anonymized_at")
        batch.drop_column("token_version")
    op.drop_index("ix_seasons_status", table_name="seasons")
    with op.batch_alter_table("seasons") as batch:
        batch.drop_column("status")
