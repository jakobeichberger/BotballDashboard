"""Teams: season details, roster, documents, print checklist; paper deadlines

Revision ID: 0029
Revises: 0028
Create Date: 2026-09-24 00:00:00

- team_season_registrations: fee and kit status, paper_required and the
  season's contact person and address.
- team_season_members: season-scoped roster (which member took part in which
  season, with that season's role).
- team_documents / team_document_versions: versioned team documents.
- print_compliance_items / print_compliance_checks: the per-season 3D-print
  checklist, ticked by mentors and verified by organizers.
- paper_deadlines: official and internal paper deadlines per season.
"""

import sqlalchemy as sa

from alembic import op

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def _id() -> sa.Column:
    return sa.Column("id", sa.String(36), primary_key=True)


def _created_at() -> sa.Column:
    return sa.Column(
        "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )


def _user_fk(name: str) -> sa.Column:
    return sa.Column(
        name, sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


def upgrade() -> None:
    with op.batch_alter_table("team_season_registrations") as batch:
        batch.add_column(
            sa.Column("fee_status", sa.String(20), nullable=False, server_default="pending")
        )
        batch.add_column(
            sa.Column("kit_status", sa.String(20), nullable=False, server_default="not_sent")
        )
        batch.add_column(
            sa.Column("paper_required", sa.Boolean(), nullable=False, server_default=sa.true())
        )
        batch.add_column(sa.Column("contact_name", sa.String(255), nullable=True))
        batch.add_column(sa.Column("contact_email", sa.String(255), nullable=True))
        batch.add_column(sa.Column("contact_phone", sa.String(50), nullable=True))
        batch.add_column(sa.Column("address", sa.Text(), nullable=True))

    op.create_table(
        "team_season_members",
        _id(),
        sa.Column(
            "registration_id",
            sa.String(36),
            sa.ForeignKey("team_season_registrations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "member_id",
            sa.String(36),
            sa.ForeignKey("team_members.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(100), nullable=True),
        sa.UniqueConstraint("registration_id", "member_id", name="uq_team_season_member"),
    )
    op.create_index(
        "ix_team_season_members_registration_id", "team_season_members", ["registration_id"]
    )
    op.create_index("ix_team_season_members_member_id", "team_season_members", ["member_id"])

    op.create_table(
        "team_documents",
        _id(),
        sa.Column(
            "team_id",
            sa.String(36),
            sa.ForeignKey("teams.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "season_id",
            sa.String(36),
            sa.ForeignKey("seasons.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("category", sa.String(30), nullable=False, server_default="other"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("current_version", sa.Integer(), nullable=False, server_default="0"),
        _user_fk("created_by"),
        _created_at(),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_team_documents_team_id", "team_documents", ["team_id"])
    op.create_index("ix_team_documents_season_id", "team_documents", ["season_id"])

    op.create_table(
        "team_document_versions",
        _id(),
        sa.Column(
            "document_id",
            sa.String(36),
            sa.ForeignKey("team_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column("media_type", sa.String(100), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        _user_fk("uploaded_by"),
        sa.Column(
            "uploaded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("document_id", "version_number", name="uq_team_document_version"),
    )
    op.create_index(
        "ix_team_document_versions_document_id", "team_document_versions", ["document_id"]
    )

    op.create_table(
        "print_compliance_items",
        _id(),
        sa.Column(
            "season_id",
            sa.String(36),
            sa.ForeignKey("seasons.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("label", sa.String(500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        _created_at(),
    )
    op.create_index("ix_print_compliance_items_season_id", "print_compliance_items", ["season_id"])

    op.create_table(
        "print_compliance_checks",
        _id(),
        sa.Column(
            "team_id",
            sa.String(36),
            sa.ForeignKey("teams.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "item_id",
            sa.String(36),
            sa.ForeignKey("print_compliance_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("checked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("note", sa.Text(), nullable=True),
        _user_fk("checked_by"),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True),
        _user_fk("verified_by"),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("team_id", "item_id", name="uq_print_compliance_check"),
    )
    op.create_index("ix_print_compliance_checks_team_id", "print_compliance_checks", ["team_id"])
    op.create_index("ix_print_compliance_checks_item_id", "print_compliance_checks", ["item_id"])

    op.create_table(
        "paper_deadlines",
        _id(),
        sa.Column(
            "season_id",
            sa.String(36),
            sa.ForeignKey("seasons.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("deadline_type", sa.String(30), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("label", sa.String(255), nullable=True),
        sa.Column("is_hard_block", sa.Boolean(), nullable=False, server_default=sa.false()),
        _created_at(),
    )
    op.create_index("ix_paper_deadlines_season_id", "paper_deadlines", ["season_id"])


def downgrade() -> None:
    op.drop_index("ix_paper_deadlines_season_id", table_name="paper_deadlines")
    op.drop_table("paper_deadlines")
    op.drop_index("ix_print_compliance_checks_item_id", table_name="print_compliance_checks")
    op.drop_index("ix_print_compliance_checks_team_id", table_name="print_compliance_checks")
    op.drop_table("print_compliance_checks")
    op.drop_index("ix_print_compliance_items_season_id", table_name="print_compliance_items")
    op.drop_table("print_compliance_items")
    op.drop_index("ix_team_document_versions_document_id", table_name="team_document_versions")
    op.drop_table("team_document_versions")
    op.drop_index("ix_team_documents_season_id", table_name="team_documents")
    op.drop_index("ix_team_documents_team_id", table_name="team_documents")
    op.drop_table("team_documents")
    op.drop_index("ix_team_season_members_member_id", table_name="team_season_members")
    op.drop_index("ix_team_season_members_registration_id", table_name="team_season_members")
    op.drop_table("team_season_members")
    with op.batch_alter_table("team_season_registrations") as batch:
        batch.drop_column("address")
        batch.drop_column("contact_phone")
        batch.drop_column("contact_email")
        batch.drop_column("contact_name")
        batch.drop_column("paper_required")
        batch.drop_column("kit_status")
        batch.drop_column("fee_status")
