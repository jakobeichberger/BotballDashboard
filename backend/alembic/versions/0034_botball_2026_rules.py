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
* timeout_cards – the one timeout card per team and tournament.
* awards: event_awards, award_categories, award_nominations, award_results
  and the permission awards:admin (granted to the admin role).
* papers.presented_on_stage, paper_versions.page_count.
* print_jobs: purpose, part_count, STL bounding box, stl_submitted.
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


_PRINT_COLUMNS = ("purpose", "part_count", "bbox_x_mm", "bbox_y_mm", "bbox_z_mm", "stl_submitted")


def _grant_awards_admin(bind) -> None:
    """Seed awards:admin and give it to the admin role (portable, no gen_random_uuid)."""
    import uuid

    permissions = sa.table(
        "permissions", sa.column("id", sa.String), sa.column("name"), sa.column("description")
    )
    roles = sa.table("roles", sa.column("id", sa.String), sa.column("name"))
    role_permissions = sa.table(
        "role_permissions", sa.column("role_id", sa.String), sa.column("permission_id", sa.String)
    )
    permission_id = bind.execute(
        sa.select(permissions.c.id).where(permissions.c.name == "awards:admin")
    ).scalar()
    if permission_id is None:
        permission_id = str(uuid.uuid4())
        bind.execute(
            permissions.insert().values(
                id=permission_id,
                name="awards:admin",
                description="Manage awards: templates, nominations, jury decisions, publishing",
            )
        )
    for (role_id,) in bind.execute(sa.select(roles.c.id).where(roles.c.name == "admin")).all():
        granted = bind.execute(
            sa.select(role_permissions.c.role_id).where(
                role_permissions.c.role_id == role_id,
                role_permissions.c.permission_id == permission_id,
            )
        ).first()
        if granted is None:
            bind.execute(
                role_permissions.insert().values(role_id=role_id, permission_id=permission_id)
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

    # ── Timeout cards ────────────────────────────────────────────────────────
    op.create_table(
        "timeout_cards",
        sa.Column("id", sa.String(36), primary_key=True),
        _fk("event_id", "events"),
        _fk("team_id", "teams"),
        sa.Column(
            "scheduled_match_id",
            sa.String(36),
            sa.ForeignKey("scheduled_matches.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("round_number", sa.Integer(), nullable=True),
        sa.Column("reason", sa.String(20), nullable=False, server_default="before_hands_off"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "recorded_by",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "used_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("event_id", "team_id", name="uq_timeout_card_event_team"),
    )

    # ── Awards ───────────────────────────────────────────────────────────────
    op.create_table(
        "event_awards",
        sa.Column(
            "event_id",
            sa.String(36),
            sa.ForeignKey("events.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("template", sa.String(20), nullable=True),
        sa.Column("published", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "award_categories",
        sa.Column("id", sa.String(36), primary_key=True),
        _fk("event_id", "events"),
        sa.Column("key", sa.String(50), nullable=False),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("kind", sa.String(10), nullable=False, server_default="judged"),
        sa.Column("source", sa.String(30), nullable=True),
        sa.Column("team_category", sa.String(20), nullable=True),
        sa.Column("places", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("per_course", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("event_id", "key", name="uq_award_category_key"),
    )
    op.create_table(
        "award_nominations",
        sa.Column("id", sa.String(36), primary_key=True),
        _fk("award_id", "award_categories"),
        _fk("team_id", "teams"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "nominated_by",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("award_id", "team_id", name="uq_award_nomination"),
    )
    op.create_table(
        "award_results",
        sa.Column("id", sa.String(36), primary_key=True),
        _fk("award_id", "award_categories"),
        _fk("team_id", "teams"),
        sa.Column("place", sa.Integer(), nullable=False),
        sa.Column("course", sa.String(8), nullable=True),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "decided_by",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "decided_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("award_id", "team_id", name="uq_award_result_team"),
    )
    _grant_awards_admin(op.get_bind())

    # ── Papers and 3D printing ───────────────────────────────────────────────
    with op.batch_alter_table("papers") as batch:
        batch.add_column(
            sa.Column("presented_on_stage", sa.Boolean(), nullable=False, server_default=sa.false())
        )
    with op.batch_alter_table("paper_versions") as batch:
        batch.add_column(sa.Column("page_count", sa.Integer(), nullable=True))
    with op.batch_alter_table("print_jobs") as batch:
        batch.add_column(
            sa.Column("purpose", sa.String(10), nullable=False, server_default="robot")
        )
        batch.add_column(sa.Column("part_count", sa.Integer(), nullable=False, server_default="1"))
        batch.add_column(sa.Column("bbox_x_mm", sa.Float(), nullable=True))
        batch.add_column(sa.Column("bbox_y_mm", sa.Float(), nullable=True))
        batch.add_column(sa.Column("bbox_z_mm", sa.Float(), nullable=True))
        batch.add_column(
            sa.Column("stl_submitted", sa.Boolean(), nullable=False, server_default=sa.false())
        )


def downgrade() -> None:
    with op.batch_alter_table("print_jobs") as batch:
        for name in _PRINT_COLUMNS:
            batch.drop_column(name)
    with op.batch_alter_table("paper_versions") as batch:
        batch.drop_column("page_count")
    with op.batch_alter_table("papers") as batch:
        batch.drop_column("presented_on_stage")

    op.execute(
        "DELETE FROM role_permissions WHERE permission_id IN "
        "(SELECT id FROM permissions WHERE name = 'awards:admin')"
    )
    op.execute("DELETE FROM permissions WHERE name = 'awards:admin'")
    op.drop_table("award_results")
    op.drop_table("award_nominations")
    op.drop_table("award_categories")
    op.drop_table("event_awards")
    op.drop_table("timeout_cards")
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
