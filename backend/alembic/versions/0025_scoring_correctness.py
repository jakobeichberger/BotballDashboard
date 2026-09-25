"""Scoring correctness: per-category ranks, red cards, durable audit trail

Revision ID: 0025
Revises: 0024
Create Date: 2026-09-24 00:00:00

* rankings: `rank` becomes nullable (a red-carded team keeps its row but has no
  place), plus `category` (ranks are computed per registration category) and
  `disqualified`.
* score_revisions: the history must survive deleting a match. `match_id` is
  now nullable with ON DELETE SET NULL instead of CASCADE, and `match_ref` /
  `team_id` keep plain copies of what the revision belonged to.
* result_revisions: a small generic audit table for DE, aerial and
  documentation results, which had no history at all.
"""

import sqlalchemy as sa

from alembic import op

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None

# SQLite's batch mode reflects the unnamed foreign keys created in 0010; this
# convention gives them a predictable name so they can be dropped.
_NAMING = {"fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"}


def _replace_match_fk(ondelete: str, nullable: bool) -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # Postgres named the inline FK from 0010 <table>_<column>_fkey; a
        # previous run of this migration named it fk_… — handle both.
        op.execute(
            "ALTER TABLE score_revisions DROP CONSTRAINT IF EXISTS score_revisions_match_id_fkey"
        )
        op.execute(
            "ALTER TABLE score_revisions "
            "DROP CONSTRAINT IF EXISTS fk_score_revisions_match_id_matches"
        )
        op.alter_column("score_revisions", "match_id", nullable=nullable)
        op.create_foreign_key(
            "fk_score_revisions_match_id_matches",
            "score_revisions",
            "matches",
            ["match_id"],
            ["id"],
            ondelete=ondelete,
        )
        return
    with op.batch_alter_table(
        "score_revisions", recreate="always", naming_convention=_NAMING
    ) as batch:
        batch.drop_constraint("fk_score_revisions_match_id_matches", type_="foreignkey")
        batch.alter_column("match_id", existing_type=sa.String(36), nullable=nullable)
        batch.create_foreign_key(
            "fk_score_revisions_match_id_matches",
            "matches",
            ["match_id"],
            ["id"],
            ondelete=ondelete,
        )


def upgrade() -> None:
    # ── rankings ──────────────────────────────────────────────────────────────
    with op.batch_alter_table("rankings") as batch:
        batch.alter_column("rank", existing_type=sa.Integer(), nullable=True)
        batch.add_column(sa.Column("category", sa.String(30), nullable=True))
        batch.add_column(
            sa.Column("disqualified", sa.Boolean(), nullable=False, server_default=sa.false())
        )

    # ── score_revisions ───────────────────────────────────────────────────────
    op.add_column("score_revisions", sa.Column("match_ref", sa.String(36), nullable=True))
    op.add_column("score_revisions", sa.Column("team_id", sa.String(36), nullable=True))
    op.execute("UPDATE score_revisions SET match_ref = match_id")
    op.execute(
        "UPDATE score_revisions SET team_id = "
        "(SELECT matches.team_id FROM matches WHERE matches.id = score_revisions.match_id)"
    )
    op.create_index("ix_score_revisions_match_ref", "score_revisions", ["match_ref"])
    _replace_match_fk("SET NULL", nullable=True)

    # ── result_revisions ──────────────────────────────────────────────────────
    op.create_table(
        "result_revisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "event_id",
            sa.String(36),
            sa.ForeignKey("events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("team_id", sa.String(36), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("previous_value", sa.JSON(), nullable=True),
        sa.Column("new_value", sa.JSON(), nullable=True),
        sa.Column(
            "changed_by",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_result_revisions_event_id", "result_revisions", ["event_id"])
    op.create_index("ix_result_revisions_team_id", "result_revisions", ["team_id"])


def downgrade() -> None:
    op.drop_index("ix_result_revisions_team_id", table_name="result_revisions")
    op.drop_index("ix_result_revisions_event_id", table_name="result_revisions")
    op.drop_table("result_revisions")

    # Detached revisions (their match was deleted) cannot satisfy the restored
    # NOT NULL + CASCADE foreign key; the old schema had no place for them.
    op.execute("DELETE FROM score_revisions WHERE match_id IS NULL")
    _replace_match_fk("CASCADE", nullable=False)
    op.drop_index("ix_score_revisions_match_ref", table_name="score_revisions")
    with op.batch_alter_table("score_revisions") as batch:
        batch.drop_column("team_id")
        batch.drop_column("match_ref")

    # Disqualified teams have no rank; give them the last place again.
    op.execute(
        "UPDATE rankings SET rank = "
        "(SELECT COUNT(*) FROM rankings AS other WHERE other.event_id = rankings.event_id) "
        "WHERE rank IS NULL"
    )
    with op.batch_alter_table("rankings") as batch:
        batch.drop_column("disqualified")
        batch.drop_column("category")
        batch.alter_column("rank", existing_type=sa.Integer(), nullable=False)
