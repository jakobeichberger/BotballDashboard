"""Add local OCR template layout and score-sheet scan workflow.

Revision ID: 0011
Revises: 0010
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for name, column_type in (
        ("page_width", sa.Integer()),
        ("page_height", sa.Integer()),
        ("anchors", sa.JSON()),
        ("field_regions", sa.JSON()),
        ("validation_rules", sa.JSON()),
    ):
        op.add_column("score_sheet_templates", sa.Column(name, column_type, nullable=True))

    op.create_table(
        "score_sheet_scans",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "event_id",
            sa.String(36),
            sa.ForeignKey("events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "template_id",
            sa.String(36),
            sa.ForeignKey("score_sheet_templates.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "scheduled_match_id",
            sa.String(36),
            sa.ForeignKey("scheduled_matches.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "team_id",
            sa.String(36),
            sa.ForeignKey("teams.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("file_url", sa.Text(), nullable=False),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="queued"),
        sa.Column("provider", sa.String(40), nullable=False, server_default="tesseract"),
        sa.Column("extracted_values", sa.JSON(), nullable=True),
        sa.Column("reviewed_values", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "accepted_match_id",
            sa.String(36),
            sa.ForeignKey("matches.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("reviewed_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('queued', 'processing', 'review', 'accepted', 'failed')",
            name="ck_score_sheet_scan_status",
        ),
    )
    op.create_index("ix_score_sheet_scans_event_id", "score_sheet_scans", ["event_id"])
    op.create_index("ix_score_sheet_scans_template_id", "score_sheet_scans", ["template_id"])
    op.create_index("ix_score_sheet_scans_team_id", "score_sheet_scans", ["team_id"])
    op.create_index("ix_score_sheet_scans_status", "score_sheet_scans", ["status"])


def downgrade() -> None:
    op.drop_table("score_sheet_scans")
    for name in (
        "validation_rules",
        "field_regions",
        "anchors",
        "page_height",
        "page_width",
    ):
        op.drop_column("score_sheet_templates", name)
