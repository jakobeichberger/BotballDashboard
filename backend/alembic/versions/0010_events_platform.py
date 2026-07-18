"""Event-centred tournament platform and data integrity constraints.

Revision ID: 0010
Revises: 0009
Create Date: 2026-07-17 16:30:00
"""

import uuid

import sqlalchemy as sa

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def _uuid() -> str:
    return str(uuid.uuid4())


def upgrade() -> None:
    op.create_table(
        "events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "season_id",
            sa.String(36),
            sa.ForeignKey("seasons.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(120), nullable=False),
        sa.Column("event_type", sa.String(40), nullable=False, server_default="regional"),
        sa.Column("timezone", sa.String(80), nullable=False, server_default="Europe/Vienna"),
        sa.Column("venue", sa.String(255), nullable=True),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="draft"),
        sa.Column("active_modules", sa.JSON(), nullable=False, server_default='["seeding"]'),
        sa.Column("public_scoreboard", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("public_schedule", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("public_results", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("public_announcements", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("table_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("slug", name="uq_events_slug"),
    )
    op.create_index("ix_events_season_id", "events", ["season_id"])
    op.create_index("ix_events_slug", "events", ["slug"])

    op.create_table(
        "event_registrations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "event_id",
            sa.String(36),
            sa.ForeignKey("events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "team_id",
            sa.String(36),
            sa.ForeignKey("teams.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "competition_level_id",
            sa.String(36),
            sa.ForeignKey("competition_levels.id"),
            nullable=True,
        ),
        sa.Column("category", sa.String(30), nullable=False, server_default="botball"),
        sa.Column("seed_number", sa.Integer(), nullable=True),
        sa.Column("checked_in_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "registered_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("event_id", "team_id", name="uq_event_registration_event_team"),
    )
    op.create_index("ix_event_registrations_event_id", "event_registrations", ["event_id"])
    op.create_index("ix_event_registrations_team_id", "event_registrations", ["team_id"])

    op.create_table(
        "event_phases",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "event_id",
            sa.String(36),
            sa.ForeignKey("events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("phase_type", sa.String(40), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(30), nullable=False, server_default="draft"),
        sa.Column("rounds", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("settings", sa.JSON(), nullable=False, server_default="{}"),
        sa.UniqueConstraint("event_id", "sort_order", name="uq_event_phase_sort_order"),
    )
    op.create_index("ix_event_phases_event_id", "event_phases", ["event_id"])

    op.create_table(
        "scheduled_matches",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "event_id",
            sa.String(36),
            sa.ForeignKey("events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "phase_id",
            sa.String(36),
            sa.ForeignKey("event_phases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("round_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("table_number", sa.Integer(), nullable=True),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_minutes", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("status", sa.String(30), nullable=False, server_default="scheduled"),
        sa.Column("bracket", sa.String(30), nullable=True),
        sa.Column(
            "next_winner_match_id",
            sa.String(36),
            sa.ForeignKey("scheduled_matches.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "next_loser_match_id",
            sa.String(36),
            sa.ForeignKey("scheduled_matches.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.UniqueConstraint("event_id", "code", name="uq_scheduled_match_event_code"),
    )
    op.create_index("ix_scheduled_matches_event_id", "scheduled_matches", ["event_id"])
    op.create_index("ix_scheduled_matches_phase_id", "scheduled_matches", ["phase_id"])

    op.create_table(
        "match_participants",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "scheduled_match_id",
            sa.String(36),
            sa.ForeignKey("scheduled_matches.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "team_id",
            sa.String(36),
            sa.ForeignKey("teams.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("side", sa.String(20), nullable=True),
        sa.Column("result", sa.String(20), nullable=True),
        sa.Column("score", sa.Float(), nullable=True),
        sa.UniqueConstraint("scheduled_match_id", "position", name="uq_match_participant_position"),
        sa.UniqueConstraint("scheduled_match_id", "team_id", name="uq_match_participant_team"),
    )
    op.create_index(
        "ix_match_participants_scheduled_match_id",
        "match_participants",
        ["scheduled_match_id"],
    )
    op.create_index("ix_match_participants_team_id", "match_participants", ["team_id"])

    bind = op.get_bind()
    seasons = sa.table(
        "seasons",
        sa.column("id", sa.String),
        sa.column("name", sa.String),
        sa.column("year", sa.Integer),
        sa.column("use_seeding", sa.Boolean),
        sa.column("use_double_elimination", sa.Boolean),
        sa.column("use_paper_scoring", sa.Boolean),
        sa.column("use_documentation_scoring", sa.Boolean),
        sa.column("use_aerial", sa.Boolean),
    )
    events = sa.table(
        "events",
        sa.column("id", sa.String),
        sa.column("season_id", sa.String),
        sa.column("name", sa.String),
        sa.column("slug", sa.String),
        sa.column("active_modules", sa.JSON),
    )
    season_rows = bind.execute(sa.select(seasons)).mappings().all()
    default_events: dict[str, str] = {}
    for season in season_rows:
        event_id = _uuid()
        default_events[season["id"]] = event_id
        modules = []
        if season["use_seeding"]:
            modules.append("seeding")
        if season["use_double_elimination"]:
            modules.append("double_elimination")
        if season["use_paper_scoring"]:
            modules.append("paper")
        if season["use_documentation_scoring"]:
            modules.append("documentation")
        if season["use_aerial"]:
            modules.append("aerial")
        bind.execute(
            events.insert().values(
                id=event_id,
                season_id=season["id"],
                name=f"{season['name']} – Standard Event",
                slug=f"season-{season['year']}-{event_id[:8]}",
                active_modules=modules or ["seeding"],
            )
        )

    old_registrations = sa.table(
        "team_season_registrations",
        sa.column("team_id", sa.String),
        sa.column("season_id", sa.String),
        sa.column("competition_level_id", sa.String),
        sa.column("category", sa.String),
        sa.column("notes", sa.Text),
    )
    new_registrations = sa.table(
        "event_registrations",
        sa.column("id", sa.String),
        sa.column("event_id", sa.String),
        sa.column("team_id", sa.String),
        sa.column("competition_level_id", sa.String),
        sa.column("category", sa.String),
        sa.column("notes", sa.Text),
    )
    for registration in bind.execute(sa.select(old_registrations)).mappings():
        bind.execute(
            new_registrations.insert().values(
                id=_uuid(),
                event_id=default_events[registration["season_id"]],
                team_id=registration["team_id"],
                competition_level_id=registration["competition_level_id"],
                category=registration["category"],
                notes=registration["notes"],
            )
        )

    old_phases = sa.table(
        "season_phases",
        sa.column("id", sa.String),
        sa.column("season_id", sa.String),
        sa.column("name", sa.String),
        sa.column("phase_type", sa.String),
        sa.column("sort_order", sa.Integer),
        sa.column("rounds", sa.Integer),
    )
    new_phases = sa.table(
        "event_phases",
        sa.column("id", sa.String),
        sa.column("event_id", sa.String),
        sa.column("name", sa.String),
        sa.column("phase_type", sa.String),
        sa.column("sort_order", sa.Integer),
        sa.column("rounds", sa.Integer),
    )
    phase_map: dict[str, str] = {}
    for phase in bind.execute(sa.select(old_phases)).mappings():
        event_phase_id = _uuid()
        phase_map[phase["id"]] = event_phase_id
        bind.execute(
            new_phases.insert().values(
                id=event_phase_id,
                event_id=default_events[phase["season_id"]],
                name=phase["name"],
                phase_type=(
                    "double_elimination"
                    if phase["phase_type"] == "elimination"
                    else phase["phase_type"]
                ),
                sort_order=phase["sort_order"],
                rounds=phase["rounds"],
            )
        )

    event_scoped_tables = (
        "matches",
        "rankings",
        "de_results",
        "aerial_results",
        "documentation_scores",
        "papers",
        "print_jobs",
        "team_season_print_quotas",
        "announcements",
    )
    for table_name in event_scoped_tables:
        op.add_column(table_name, sa.Column("event_id", sa.String(36), nullable=True))
        op.create_foreign_key(
            f"fk_{table_name}_event_id",
            table_name,
            "events",
            ["event_id"],
            ["id"],
            ondelete="CASCADE",
        )
        op.create_index(f"ix_{table_name}_event_id", table_name, ["event_id"])
        table = sa.table(
            table_name, sa.column("season_id", sa.String), sa.column("event_id", sa.String)
        )
        for season_id, event_id in default_events.items():
            bind.execute(
                table.update().where(table.c.season_id == season_id).values(event_id=event_id)
            )

    for table_name in (
        "matches",
        "rankings",
        "de_results",
        "aerial_results",
        "documentation_scores",
    ):
        op.alter_column(table_name, "event_id", nullable=False)

    op.add_column("scoring_schemas", sa.Column("event_id", sa.String(36), nullable=True))
    op.create_foreign_key(
        "fk_scoring_schemas_event_id",
        "scoring_schemas",
        "events",
        ["event_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_scoring_schemas_event_id", "scoring_schemas", ["event_id"])

    op.add_column("matches", sa.Column("scheduled_match_id", sa.String(36), nullable=True))
    op.create_foreign_key(
        "fk_matches_scheduled_match_id",
        "matches",
        "scheduled_matches",
        ["scheduled_match_id"],
        ["id"],
        ondelete="SET NULL",
    )
    for table_name in ("matches", "rankings"):
        op.add_column(table_name, sa.Column("event_phase_id", sa.String(36), nullable=True))
        op.create_foreign_key(
            f"fk_{table_name}_event_phase_id",
            table_name,
            "event_phases",
            ["event_phase_id"],
            ["id"],
            ondelete="SET NULL",
        )
        op.create_index(f"ix_{table_name}_event_phase_id", table_name, ["event_phase_id"])
        scoped_table = sa.table(
            table_name,
            sa.column("phase_id", sa.String),
            sa.column("event_phase_id", sa.String),
        )
        for legacy_phase_id, event_phase_id in phase_map.items():
            bind.execute(
                scoped_table.update()
                .where(scoped_table.c.phase_id == legacy_phase_id)
                .values(event_phase_id=event_phase_id)
            )
    op.add_column("matches", sa.Column("schema_snapshot", sa.JSON(), nullable=True))
    op.add_column("matches", sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("matches", sa.Column("idempotency_key", sa.String(100), nullable=True))
    op.create_unique_constraint("uq_matches_idempotency_key", "matches", ["idempotency_key"])

    op.create_table(
        "score_revisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "match_id",
            sa.String(36),
            sa.ForeignKey("matches.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "event_id",
            sa.String(36),
            sa.ForeignKey("events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("previous_raw_scores", sa.JSON(), nullable=True),
        sa.Column("new_raw_scores", sa.JSON(), nullable=False),
        sa.Column("previous_total_score", sa.Float(), nullable=True),
        sa.Column("new_total_score", sa.Float(), nullable=False),
        sa.Column("previous_value", sa.JSON(), nullable=True),
        sa.Column("new_value", sa.JSON(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("changed_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("match_id", "revision", name="uq_score_revision_match_revision"),
    )
    op.create_index("ix_score_revisions_match_id", "score_revisions", ["match_id"])
    op.create_index("ix_score_revisions_event_id", "score_revisions", ["event_id"])

    matches = sa.table(
        "matches",
        sa.column("id", sa.String),
        sa.column("event_id", sa.String),
        sa.column("raw_scores", sa.JSON),
        sa.column("total_score", sa.Float),
        sa.column("is_disqualified", sa.Boolean),
        sa.column("yellow_card", sa.Boolean),
        sa.column("red_card", sa.Boolean),
        sa.column("notes", sa.Text),
        sa.column("entered_by", sa.String),
    )
    revisions = sa.table(
        "score_revisions",
        sa.column("id", sa.String),
        sa.column("match_id", sa.String),
        sa.column("event_id", sa.String),
        sa.column("revision", sa.Integer),
        sa.column("new_raw_scores", sa.JSON),
        sa.column("new_total_score", sa.Float),
        sa.column("new_value", sa.JSON),
        sa.column("changed_by", sa.String),
    )
    for match in bind.execute(sa.select(matches)).mappings():
        value = {
            "raw_scores": match["raw_scores"] or {},
            "total_score": match["total_score"],
            "is_disqualified": match["is_disqualified"],
            "yellow_card": match["yellow_card"],
            "red_card": match["red_card"],
            "notes": match["notes"],
        }
        bind.execute(
            revisions.insert().values(
                id=_uuid(),
                match_id=match["id"],
                event_id=match["event_id"],
                revision=1,
                new_raw_scores=match["raw_scores"] or {},
                new_total_score=match["total_score"],
                new_value=value,
                changed_by=match["entered_by"],
            )
        )

    op.create_unique_constraint(
        "uq_team_registration_team_season",
        "team_season_registrations",
        ["team_id", "season_id"],
    )
    op.create_unique_constraint(
        "uq_reviewer_assignment_paper_reviewer",
        "reviewer_assignments",
        ["paper_id", "reviewer_id"],
    )
    op.create_unique_constraint(
        "uq_paper_review_revision",
        "paper_reviews",
        ["paper_id", "reviewer_id", "revision_number"],
    )
    op.create_unique_constraint(
        "uq_print_quota_event_team",
        "team_season_print_quotas",
        ["event_id", "team_id"],
    )
    op.create_unique_constraint(
        "uq_ranking_event_team_phase_level",
        "rankings",
        ["event_id", "team_id", "event_phase_id", "competition_level_id"],
    )
    op.create_unique_constraint(
        "uq_scoring_schema_scope_version",
        "scoring_schemas",
        ["season_id", "event_id", "competition_level_id", "version"],
    )
    for table_name, old_name, new_name in (
        ("de_results", "uq_de_result_season_team", "uq_de_result_event_team"),
        ("aerial_results", "uq_aerial_result_season_team", "uq_aerial_result_event_team"),
        ("documentation_scores", "uq_doc_score_season_team", "uq_doc_score_event_team"),
    ):
        op.drop_constraint(old_name, table_name, type_="unique")
        op.create_unique_constraint(new_name, table_name, ["event_id", "team_id"])

    permissions = sa.table(
        "permissions",
        sa.column("id", sa.String),
        sa.column("name", sa.String),
        sa.column("description", sa.Text),
    )
    roles = sa.table("roles", sa.column("id", sa.String), sa.column("name", sa.String))
    role_permissions = sa.table(
        "role_permissions", sa.column("role_id", sa.String), sa.column("permission_id", sa.String)
    )
    permission_ids: dict[str, str] = {}
    for name, description in (
        ("events:read", "View events, registrations, phases and schedules"),
        ("events:write", "Manage events, registrations, phases and schedules"),
        ("events:admin", "Delete events and change publication settings"),
    ):
        permission_id = _uuid()
        permission_ids[name] = permission_id
        bind.execute(
            permissions.insert().values(id=permission_id, name=name, description=description)
        )
    role_rows = {row.name: row.id for row in bind.execute(sa.select(roles)).all()}
    grants = {
        "admin": tuple(permission_ids),
        "juror": ("events:read", "events:write"),
        "reviewer": ("events:read",),
        "mentor": ("events:read",),
        "guest": ("events:read",),
    }
    for role_name, permission_names in grants.items():
        role_id = role_rows.get(role_name)
        if role_id:
            for permission_name in permission_names:
                bind.execute(
                    role_permissions.insert().values(
                        role_id=role_id, permission_id=permission_ids[permission_name]
                    )
                )


def downgrade() -> None:
    for table_name, old_name, new_name in reversed(
        (
            ("de_results", "uq_de_result_season_team", "uq_de_result_event_team"),
            ("aerial_results", "uq_aerial_result_season_team", "uq_aerial_result_event_team"),
            ("documentation_scores", "uq_doc_score_season_team", "uq_doc_score_event_team"),
        )
    ):
        op.drop_constraint(new_name, table_name, type_="unique")
        op.create_unique_constraint(old_name, table_name, ["season_id", "team_id"])
    op.drop_constraint("uq_scoring_schema_scope_version", "scoring_schemas", type_="unique")
    op.drop_constraint("uq_ranking_event_team_phase_level", "rankings", type_="unique")
    op.drop_constraint("uq_print_quota_event_team", "team_season_print_quotas", type_="unique")
    op.drop_constraint("uq_paper_review_revision", "paper_reviews", type_="unique")
    op.drop_constraint(
        "uq_reviewer_assignment_paper_reviewer", "reviewer_assignments", type_="unique"
    )
    op.drop_constraint(
        "uq_team_registration_team_season", "team_season_registrations", type_="unique"
    )
    op.drop_table("score_revisions")
    op.drop_constraint("uq_matches_idempotency_key", "matches", type_="unique")
    op.drop_column("matches", "idempotency_key")
    op.drop_column("matches", "version")
    op.drop_column("matches", "schema_snapshot")
    op.drop_constraint("fk_matches_scheduled_match_id", "matches", type_="foreignkey")
    op.drop_column("matches", "scheduled_match_id")
    for table_name in ("rankings", "matches"):
        op.drop_index(f"ix_{table_name}_event_phase_id", table_name=table_name)
        op.drop_constraint(f"fk_{table_name}_event_phase_id", table_name, type_="foreignkey")
        op.drop_column(table_name, "event_phase_id")
    op.drop_index("ix_scoring_schemas_event_id", table_name="scoring_schemas")
    op.drop_constraint("fk_scoring_schemas_event_id", "scoring_schemas", type_="foreignkey")
    op.drop_column("scoring_schemas", "event_id")
    for table_name in reversed(
        (
            "matches",
            "rankings",
            "de_results",
            "aerial_results",
            "documentation_scores",
            "papers",
            "print_jobs",
            "team_season_print_quotas",
            "announcements",
        )
    ):
        op.drop_index(f"ix_{table_name}_event_id", table_name=table_name)
        op.drop_constraint(f"fk_{table_name}_event_id", table_name, type_="foreignkey")
        op.drop_column(table_name, "event_id")
    op.drop_table("match_participants")
    op.drop_table("scheduled_matches")
    op.drop_table("event_phases")
    op.drop_table("event_registrations")
    op.drop_table("events")
