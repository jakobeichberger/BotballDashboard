"""Competition modules: season feature flags, team categories, DE/aerial/doc scoring

Revision ID: 0009
Revises: 0008
Create Date: 2026-01-01 00:07:00
"""
from alembic import op
import sqlalchemy as sa

revision = "0009"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Season feature flags ──────────────────────────────────────────────────
    op.add_column("seasons", sa.Column("use_seeding", sa.Boolean(), nullable=False, server_default="true"))
    op.add_column("seasons", sa.Column("use_double_elimination", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("seasons", sa.Column("use_paper_scoring", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("seasons", sa.Column("use_documentation_scoring", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("seasons", sa.Column("use_aerial", sa.Boolean(), nullable=False, server_default="false"))
    # JSON list of active team categories: ["botball", "open", "aerial", "jbc"]
    op.add_column("seasons", sa.Column("active_categories", sa.JSON(), nullable=False, server_default='["botball"]'))

    # ── Team category per season registration ─────────────────────────────────
    op.add_column(
        "team_season_registrations",
        sa.Column("category", sa.String(20), nullable=False, server_default="botball"),
    )

    # ── Paper: final numeric score + rank ─────────────────────────────────────
    op.add_column("papers", sa.Column("final_score", sa.Float(), nullable=True))
    op.add_column("papers", sa.Column("paper_rank", sa.Integer(), nullable=True))

    # ── Double Elimination results ────────────────────────────────────────────
    op.create_table(
        "de_results",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("season_id", sa.String(36), sa.ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("team_id", sa.String(36), sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("bracket", sa.String(1), nullable=False),  # "A" | "B"
        sa.Column("de_rank", sa.Integer(), nullable=True),
        sa.Column("bracket_score", sa.Float(), nullable=True),  # normalized 0-1 within bracket
        sa.Column("de_score", sa.Float(), nullable=True),       # final normalized score
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("season_id", "team_id", name="uq_de_result_season_team"),
    )

    # ── Aerial competition results ────────────────────────────────────────────
    op.create_table(
        "aerial_results",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("season_id", sa.String(36), sa.ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("team_id", sa.String(36), sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("run1", sa.Float(), nullable=True),
        sa.Column("run2", sa.Float(), nullable=True),
        sa.Column("run3", sa.Float(), nullable=True),
        sa.Column("run4", sa.Float(), nullable=True),
        sa.Column("score", sa.Float(), nullable=True),   # average of best 2 runs
        sa.Column("rank", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("season_id", "team_id", name="uq_aerial_result_season_team"),
    )

    # ── Documentation scoring ─────────────────────────────────────────────────
    op.create_table(
        "documentation_scores",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("season_id", sa.String(36), sa.ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("team_id", sa.String(36), sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("part1", sa.Float(), nullable=True),   # Doc P1 (0-100)
        sa.Column("part2", sa.Float(), nullable=True),   # Doc P2 (0-100)
        sa.Column("part3", sa.Float(), nullable=True),   # Doc P3 (0-100)
        sa.Column("onsite", sa.Float(), nullable=True),  # Onsite evaluation (0-100)
        sa.Column("doc_score", sa.Float(), nullable=True),  # avg(p1,p2,p3)/100
        sa.Column("doc_rank", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("season_id", "team_id", name="uq_doc_score_season_team"),
    )


def downgrade() -> None:
    op.drop_table("documentation_scores")
    op.drop_table("aerial_results")
    op.drop_table("de_results")
    op.drop_column("papers", "paper_rank")
    op.drop_column("papers", "final_score")
    op.drop_column("team_season_registrations", "category")
    op.drop_column("seasons", "active_categories")
    op.drop_column("seasons", "use_aerial")
    op.drop_column("seasons", "use_documentation_scoring")
    op.drop_column("seasons", "use_paper_scoring")
    op.drop_column("seasons", "use_double_elimination")
    op.drop_column("seasons", "use_seeding")
