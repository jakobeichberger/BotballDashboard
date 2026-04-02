"""Paper review module: papers, reviewer_assignments, paper_reviews

Revision ID: 0006
Revises: 0005
Create Date: 2026-01-01 00:04:00
"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "papers",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("season_id", sa.String(36), sa.ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("team_id", sa.String(36), sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("abstract", sa.Text, nullable=True),
        sa.Column("competition_level_id", sa.String(36), sa.ForeignKey("competition_levels.id"), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="draft"),
        sa.Column("file_url", sa.Text, nullable=True),
        sa.Column("file_name", sa.String(255), nullable=True),
        sa.Column("file_size_bytes", sa.Integer, nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("submitted_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("revision_number", sa.Integer, nullable=False, server_default="1"),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_papers_season_id", "papers", ["season_id"])
    op.create_index("ix_papers_team_id", "papers", ["team_id"])

    op.create_table(
        "reviewer_assignments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("paper_id", sa.String(36), sa.ForeignKey("papers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("reviewer_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("assigned_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
    )
    op.create_index("ix_reviewer_assignments_paper_id", "reviewer_assignments", ["paper_id"])

    op.create_table(
        "paper_reviews",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("paper_id", sa.String(36), sa.ForeignKey("papers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("reviewer_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("revision_number", sa.Integer, nullable=False, server_default="1"),
        sa.Column("score_content", sa.Float, nullable=True),
        sa.Column("score_methodology", sa.Float, nullable=True),
        sa.Column("score_presentation", sa.Float, nullable=True),
        sa.Column("score_originality", sa.Float, nullable=True),
        sa.Column("total_score", sa.Float, nullable=True),
        sa.Column("comments", sa.Text, nullable=True),
        sa.Column("private_notes", sa.Text, nullable=True),
        sa.Column("recommendation", sa.String(50), nullable=True),
        sa.Column("is_submitted", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_paper_reviews_paper_id", "paper_reviews", ["paper_id"])


def downgrade() -> None:
    op.drop_table("paper_reviews")
    op.drop_table("reviewer_assignments")
    op.drop_table("papers")
