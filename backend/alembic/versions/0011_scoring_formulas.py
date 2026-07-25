"""Configurable scoring formulas and bracket weights

Revision ID: 0011
Revises: 0010
Create Date: 2026-07-25

Scoring stops being hard-coded: each season/category carries the formulas from
that year's game document, so an ECER amendment is a data change rather than a
code change.
"""

import sqlalchemy as sa

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scoring_formulas",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "season_id",
            sa.String(36),
            sa.ForeignKey("seasons.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("category", sa.String(20), nullable=False, server_default="botball"),
        sa.Column("key", sa.String(50), nullable=False),
        sa.Column("expression", sa.Text, nullable=False),
        sa.Column("label", sa.String(255), nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("season_id", "category", "key", name="uq_scoring_formula_key"),
    )
    op.create_index("ix_scoring_formulas_season_id", "scoring_formulas", ["season_id"])

    op.create_table(
        "scoring_bracket_weights",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "season_id",
            sa.String(36),
            sa.ForeignKey("seasons.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("category", sa.String(20), nullable=False, server_default="botball"),
        sa.Column("bracket", sa.String(4), nullable=False),
        sa.Column("weight", sa.Float, nullable=False, server_default="1.0"),
        sa.UniqueConstraint("season_id", "category", "bracket", name="uq_scoring_bracket_weight"),
    )
    op.create_index(
        "ix_scoring_bracket_weights_season_id", "scoring_bracket_weights", ["season_id"]
    )

    op.execute("""
        INSERT INTO permissions (id, name, description) VALUES
        (gen_random_uuid()::text, 'scoring:formulas', 'Edit scoring formulas')
        ON CONFLICT (name) DO NOTHING
    """)
    op.execute("""
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id FROM roles r, permissions p
        WHERE r.name = 'admin' AND p.name = 'scoring:formulas'
        AND NOT EXISTS (
            SELECT 1 FROM role_permissions rp
            WHERE rp.role_id = r.id AND rp.permission_id = p.id
        )
    """)


def downgrade() -> None:
    op.execute("""
        DELETE FROM role_permissions
        WHERE permission_id IN (SELECT id FROM permissions WHERE name = 'scoring:formulas')
    """)
    op.execute("DELETE FROM permissions WHERE name = 'scoring:formulas'")
    op.drop_index("ix_scoring_bracket_weights_season_id", table_name="scoring_bracket_weights")
    op.drop_table("scoring_bracket_weights")
    op.drop_index("ix_scoring_formulas_season_id", table_name="scoring_formulas")
    op.drop_table("scoring_formulas")
