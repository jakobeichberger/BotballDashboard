"""Unique constraint on team_season_print_quotas(team_id, season_id)

Revision ID: 0016
Revises: 0015
Create Date: 2026-07-16 00:00:00

_get_or_create_quota does a check-then-insert and the table only had a
non-unique index, so two concurrent requests could each insert a row; every
later read then failed with MultipleResultsFound (a permanent 500 for that
team+season). Deduplicate, then let the database enforce it.
"""
from alembic import op
import sqlalchemy as sa

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Collapse any duplicates that already exist, keeping the row with the most
    # recorded usage (ties broken by id) so no consumption is lost.
    op.execute(
        """
        DELETE FROM team_season_print_quotas a
        USING team_season_print_quotas b
        WHERE a.team_id = b.team_id
          AND a.season_id = b.season_id
          AND (a.used_parts, a.used_grams, a.id) < (b.used_parts, b.used_grams, b.id)
        """
    )
    op.drop_index("ix_print_quotas_team_season", table_name="team_season_print_quotas")
    op.create_unique_constraint(
        "uq_print_quotas_team_season", "team_season_print_quotas", ["team_id", "season_id"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_print_quotas_team_season", "team_season_print_quotas", type_="unique")
    op.create_index("ix_print_quotas_team_season", "team_season_print_quotas", ["team_id", "season_id"])
