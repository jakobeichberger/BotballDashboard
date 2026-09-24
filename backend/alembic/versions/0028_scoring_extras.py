"""Scoring extras: structured score sheets, special rules, tie-breakers,
scouting, GCER qualification, referee checklist and parts challenges

Revision ID: 0028
Revises: 0027
Create Date: 2026-09-24 00:00:00

* scoring_schemas.definition – structured sheet (sections, area multipliers,
  either-or groups, sides A/B); NULL for the existing flat schemas.
* matches – sheet_score / bonus_score (25 % end-of-game contact), round_lost
  (+ reason), end_contact, tiebreak_values, checklist. Existing rows get
  sheet_score = total_score, so their totals are unchanged.
* rankings.tiebreaker – which tie-breaker placed a team.
* competition_levels.level_order / qualifies_from_level_id.
* New tables: scoring_rule_sets, external_teams, scouting_notes,
  scouting_observations, team_qualifications, parts_challenges.
"""

import sqlalchemy as sa

from alembic import op

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def _created_at() -> sa.Column:
    return sa.Column(
        "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )


def upgrade() -> None:
    with op.batch_alter_table("scoring_schemas") as batch:
        batch.add_column(sa.Column("definition", sa.JSON(), nullable=True))

    with op.batch_alter_table("matches") as batch:
        batch.add_column(sa.Column("sheet_score", sa.Float(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("bonus_score", sa.Float(), nullable=False, server_default="0"))
        batch.add_column(
            sa.Column("end_contact", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch.add_column(
            sa.Column("round_lost", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch.add_column(sa.Column("round_lost_reason", sa.String(40), nullable=True))
        batch.add_column(
            sa.Column("tiebreak_values", sa.JSON(), nullable=False, server_default="{}")
        )
        batch.add_column(sa.Column("checklist", sa.JSON(), nullable=True))
    op.execute("UPDATE matches SET sheet_score = total_score")

    with op.batch_alter_table("rankings") as batch:
        batch.add_column(sa.Column("tiebreaker", sa.String(255), nullable=True))

    with op.batch_alter_table("competition_levels") as batch:
        batch.add_column(sa.Column("level_order", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("qualifies_from_level_id", sa.String(36), nullable=True))
        batch.create_foreign_key(
            "fk_competition_levels_qualifies_from",
            "competition_levels",
            ["qualifies_from_level_id"],
            ["id"],
            ondelete="SET NULL",
        )
    # Known levels get their natural order; GCER qualifies from ECER.
    op.execute("UPDATE competition_levels SET level_order = 1 WHERE code = 'ECER'")
    op.execute("UPDATE competition_levels SET level_order = 2 WHERE code = 'GCER'")
    op.execute(
        "UPDATE competition_levels SET qualifies_from_level_id = "
        "(SELECT id FROM competition_levels WHERE code = 'ECER') WHERE code = 'GCER'"
    )

    op.create_table(
        "scoring_rule_sets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "season_id",
            sa.String(36),
            sa.ForeignKey("seasons.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("tiebreakers", sa.JSON(), nullable=False),
        sa.Column("finals_replay", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("end_contact_bonus_percent", sa.Float(), nullable=False, server_default="25"),
        sa.Column("referee_checklist", sa.JSON(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("season_id", name="uq_scoring_rule_set_season"),
    )
    op.create_index("ix_scoring_rule_sets_season_id", "scoring_rule_sets", ["season_id"])

    op.create_table(
        "external_teams",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "season_id",
            sa.String(36),
            sa.ForeignKey("seasons.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("number", sa.String(50), nullable=True),
        sa.Column("country", sa.String(100), nullable=True),
        sa.Column("school", sa.String(255), nullable=True),
        sa.Column("source", sa.String(20), nullable=False, server_default="observed"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_by",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        _created_at(),
    )
    op.create_index("ix_external_teams_season_id", "external_teams", ["season_id"])

    for table, extra in (
        (
            "scouting_notes",
            [
                sa.Column("body", sa.Text(), nullable=False),
                sa.Column("threat_level", sa.Integer(), nullable=True),
                _created_at(),
                sa.Column(
                    "updated_at",
                    sa.DateTime(timezone=True),
                    server_default=sa.func.now(),
                    nullable=False,
                ),
            ],
        ),
        (
            "scouting_observations",
            [
                sa.Column("phase", sa.String(30), nullable=False, server_default="seeding"),
                sa.Column("round_number", sa.Integer(), nullable=True),
                sa.Column("score", sa.Float(), nullable=False),
                sa.Column("notes", sa.Text(), nullable=True),
                _created_at(),
            ],
        ),
    ):
        op.create_table(
            table,
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column(
                "event_id",
                sa.String(36),
                sa.ForeignKey("events.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "external_team_id",
                sa.String(36),
                sa.ForeignKey("external_teams.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "owner_team_id",
                sa.String(36),
                sa.ForeignKey("teams.id", ondelete="CASCADE"),
                nullable=True,
            ),
            sa.Column(
                "author_id",
                sa.String(36),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            *extra,
        )
        for column in ("event_id", "external_team_id", "owner_team_id"):
            op.create_index(f"ix_{table}_{column}", table, [column])

    op.create_table(
        "team_qualifications",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "season_id",
            sa.String(36),
            sa.ForeignKey("seasons.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "team_id", sa.String(36), sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "level_id",
            sa.String(36),
            sa.ForeignKey("competition_levels.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "from_level_id",
            sa.String(36),
            sa.ForeignKey("competition_levels.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "source_event_id",
            sa.String(36),
            sa.ForeignKey("events.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "qualified_by",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        _created_at(),
        sa.UniqueConstraint("season_id", "team_id", "level_id", name="uq_team_qualification"),
    )
    op.create_index("ix_team_qualifications_season_id", "team_qualifications", ["season_id"])
    op.create_index("ix_team_qualifications_team_id", "team_qualifications", ["team_id"])

    op.create_table(
        "parts_challenges",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "event_id",
            sa.String(36),
            sa.ForeignKey("events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "scheduled_match_id",
            sa.String(36),
            sa.ForeignKey("scheduled_matches.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "challenger_team_id",
            sa.String(36),
            sa.ForeignKey("teams.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "challenged_team_id",
            sa.String(36),
            sa.ForeignKey("teams.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("upheld", sa.Boolean(), nullable=True),
        sa.Column("ruling_note", sa.Text(), nullable=True),
        sa.Column(
            "decided_by",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_by",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        _created_at(),
    )
    op.create_index("ix_parts_challenges_event_id", "parts_challenges", ["event_id"])


def downgrade() -> None:
    op.drop_index("ix_parts_challenges_event_id", table_name="parts_challenges")
    op.drop_table("parts_challenges")
    op.drop_index("ix_team_qualifications_team_id", table_name="team_qualifications")
    op.drop_index("ix_team_qualifications_season_id", table_name="team_qualifications")
    op.drop_table("team_qualifications")
    for table in ("scouting_observations", "scouting_notes"):
        for column in ("event_id", "external_team_id", "owner_team_id"):
            op.drop_index(f"ix_{table}_{column}", table_name=table)
        op.drop_table(table)
    op.drop_index("ix_external_teams_season_id", table_name="external_teams")
    op.drop_table("external_teams")
    op.drop_index("ix_scoring_rule_sets_season_id", table_name="scoring_rule_sets")
    op.drop_table("scoring_rule_sets")

    with op.batch_alter_table("competition_levels") as batch:
        batch.drop_constraint("fk_competition_levels_qualifies_from", type_="foreignkey")
        batch.drop_column("qualifies_from_level_id")
        batch.drop_column("level_order")
    with op.batch_alter_table("rankings") as batch:
        batch.drop_column("tiebreaker")
    with op.batch_alter_table("matches") as batch:
        for column in (
            "checklist",
            "tiebreak_values",
            "round_lost_reason",
            "round_lost",
            "end_contact",
            "bonus_score",
            "sheet_score",
        ):
            batch.drop_column(column)
    with op.batch_alter_table("scoring_schemas") as batch:
        batch.drop_column("definition")
