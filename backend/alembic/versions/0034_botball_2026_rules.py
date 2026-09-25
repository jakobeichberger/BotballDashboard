"""Botball 2026 rules: categories, aerial runs, JBC, awards, 2026 extras

Revision ID: 0034
Revises: 0033

* season_categories – the category registry of a season (key, labels DE/EN,
  kind, formula preset, aerial run counts, per-bracket ranking). Seasons
  without rows keep using the defaults (Botball, ECER Open, Aerial Junior,
  Aerial Senior = the historical key "aerial", Junior Botball Challenge), so
  every stored category value stays valid.
* aerial_results.run1..run4 become one JSON list ``runs`` (ECER 2026 flew six
  runs). The downgrade keeps the first four runs.
* scoring_rule_sets: ``seeding_tiebreakers`` (off: seeding ties share a rank)
  and ``doc_max_points`` (rubric maxima of the documentation periods).
* jbc_results – Junior Botball Challenge points for solved challenges.
"""

import sqlalchemy as sa

from alembic import op

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None

_RUN_COLUMNS = ("run1", "run2", "run3", "run4")


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def _fk(column: str, table: str, *, nullable: bool = False, ondelete: str = "CASCADE"):
    return sa.Column(
        column,
        sa.String(36),
        sa.ForeignKey(f"{table}.id", ondelete=ondelete),
        nullable=nullable,
        index=True,
    )


def upgrade() -> None:
    op.create_table(
        "season_categories",
        sa.Column("id", sa.String(36), primary_key=True),
        _fk("season_id", "seasons"),
        sa.Column("key", sa.String(20), nullable=False),
        sa.Column("label_de", sa.String(100), nullable=False),
        sa.Column("label_en", sa.String(100), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False, server_default="custom"),
        sa.Column("formula_preset", sa.String(50), nullable=True),
        sa.Column("run_count", sa.Integer(), nullable=True),
        sa.Column("counted_runs", sa.Integer(), nullable=True),
        sa.Column("rank_per_bracket", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("season_id", "key", name="uq_season_category_key"),
    )

    # ── Aerial runs as a list ────────────────────────────────────────────────
    with op.batch_alter_table("aerial_results") as batch:
        batch.add_column(
            sa.Column("runs", sa.JSON(), nullable=False, server_default=sa.text("'[]'"))
        )
    aerial = sa.table(
        "aerial_results",
        sa.column("id", sa.String),
        sa.column("runs", sa.JSON),
        *(sa.column(name, sa.Float) for name in _RUN_COLUMNS),
    )
    bind = op.get_bind()
    rows = bind.execute(sa.select(aerial.c.id, *(aerial.c[name] for name in _RUN_COLUMNS))).all()
    for row in rows:
        runs = [row[i + 1] for i in range(len(_RUN_COLUMNS))]
        while runs and runs[-1] is None:
            runs.pop()
        bind.execute(aerial.update().where(aerial.c.id == row[0]).values(runs=runs))
    with op.batch_alter_table("aerial_results") as batch:
        for name in _RUN_COLUMNS:
            batch.drop_column(name)

    # ── Season rules ─────────────────────────────────────────────────────────
    with op.batch_alter_table("scoring_rule_sets") as batch:
        batch.add_column(
            sa.Column(
                "seeding_tiebreakers", sa.Boolean(), nullable=False, server_default=sa.false()
            )
        )
        batch.add_column(sa.Column("doc_max_points", sa.JSON(), nullable=True))

    # ── Junior Botball Challenge ─────────────────────────────────────────────
    op.create_table(
        "jbc_results",
        sa.Column("id", sa.String(36), primary_key=True),
        _fk("season_id", "seasons"),
        _fk("event_id", "events"),
        _fk("team_id", "teams"),
        sa.Column("points", sa.Float(), nullable=True),
        sa.Column("challenges", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("rank", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        *_timestamps(),
        sa.UniqueConstraint("event_id", "team_id", name="uq_jbc_result_event_team"),
    )


def downgrade() -> None:
    op.drop_table("jbc_results")

    with op.batch_alter_table("scoring_rule_sets") as batch:
        batch.drop_column("doc_max_points")
        batch.drop_column("seeding_tiebreakers")

    with op.batch_alter_table("aerial_results") as batch:
        for name in _RUN_COLUMNS:
            batch.add_column(sa.Column(name, sa.Float(), nullable=True))
    aerial = sa.table(
        "aerial_results",
        sa.column("id", sa.String),
        sa.column("runs", sa.JSON),
        *(sa.column(name, sa.Float) for name in _RUN_COLUMNS),
    )
    bind = op.get_bind()
    for row_id, runs in bind.execute(sa.select(aerial.c.id, aerial.c.runs)).all():
        values = list(runs or [])[: len(_RUN_COLUMNS)]
        values += [None] * (len(_RUN_COLUMNS) - len(values))
        bind.execute(
            aerial.update()
            .where(aerial.c.id == row_id)
            .values(**dict(zip(_RUN_COLUMNS, values, strict=True)))
        )
    with op.batch_alter_table("aerial_results") as batch:
        batch.drop_column("runs")

    op.drop_table("season_categories")
