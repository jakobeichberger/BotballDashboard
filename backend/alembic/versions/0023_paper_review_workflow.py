"""Paper review: PDF versions, spec review criteria, one paper per team/season

Revision ID: 0023
Revises: 0022
Create Date: 2026-09-24 00:00:00

- paper_versions: every upload is kept as its own row and file. Existing
  uploads become version 1 (they live at papers/<paper_id>/<file_name>).
- papers: current_version, format deduction, finalized_at, and a unique
  (season_id, team_id) constraint so the ranking has exactly one paper per team.
- reviewer_assignments / paper_reviews remember the version they refer to.
- paper_reviews: the five criteria of the spec (content, implementation,
  results, language, format) with a comment each, plus revision_notes.
  methodology -> implementation and presentation -> language carry over;
  originality has no counterpart and is dropped.
"""

import uuid

import sqlalchemy as sa

from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None

_NEW_CRITERIA = ("implementation", "results", "language", "format")
_ALL_CRITERIA = ("content", *_NEW_CRITERIA)


def upgrade() -> None:
    bind = op.get_bind()

    duplicates = bind.execute(
        sa.text(
            "SELECT season_id, team_id, COUNT(*) FROM papers "
            "GROUP BY season_id, team_id HAVING COUNT(*) > 1"
        )
    ).fetchall()
    if duplicates:
        pairs = ", ".join(f"season {row[0]} / team {row[1]}" for row in duplicates)
        raise RuntimeError(
            "Cannot enforce one paper per team and season: duplicates exist for "
            f"{pairs}. Delete or move the surplus papers, then rerun the migration."
        )

    with op.batch_alter_table("papers") as batch:
        batch.add_column(sa.Column("current_version", sa.Integer(), nullable=True))
        batch.add_column(
            sa.Column("format_deduction", sa.Float(), nullable=False, server_default="0")
        )
        batch.add_column(sa.Column("format_deduction_reason", sa.Text(), nullable=True))
        batch.add_column(sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True))
        batch.create_unique_constraint("uq_paper_season_team", ["season_id", "team_id"])

    op.create_table(
        "paper_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "paper_id",
            sa.String(36),
            sa.ForeignKey("papers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False),
        sa.Column(
            "uploaded_by",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "uploaded_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("paper_id", "version_number", name="uq_paper_version_number"),
    )
    op.create_index("ix_paper_versions_paper_id", "paper_versions", ["paper_id"])

    # Existing single-file uploads become version 1.
    # Timestamps are copied in SQL so they never round-trip through Python
    # (SQLite hands them back as strings).
    rows = bind.execute(
        sa.text(
            "SELECT id, file_name, file_size_bytes, revision_number, submitted_by "
            "FROM papers WHERE file_name IS NOT NULL"
        )
    ).fetchall()
    versions = sa.table(
        "paper_versions",
        sa.column("id", sa.String),
        sa.column("paper_id", sa.String),
        sa.column("version_number", sa.Integer),
        sa.column("revision_number", sa.Integer),
        sa.column("file_name", sa.String),
        sa.column("storage_path", sa.Text),
        sa.column("file_size_bytes", sa.Integer),
        sa.column("uploaded_by", sa.String),
    )
    if rows:
        op.bulk_insert(
            versions,
            [
                {
                    "id": str(uuid.uuid4()),
                    "paper_id": row[0],
                    "version_number": 1,
                    "revision_number": row[3] or 1,
                    "file_name": row[1],
                    "storage_path": f"papers/{row[0]}/{row[1]}",
                    "file_size_bytes": row[2] or 0,
                    "uploaded_by": row[4],
                }
                for row in rows
            ],
        )
        op.execute(
            "UPDATE paper_versions SET "
            "uploaded_at = (SELECT updated_at FROM papers WHERE papers.id = paper_versions.paper_id), "
            "submitted_at = (SELECT submitted_at FROM papers WHERE papers.id = paper_versions.paper_id)"
        )
        op.execute("UPDATE papers SET current_version = 1 WHERE file_name IS NOT NULL")

    with op.batch_alter_table("reviewer_assignments") as batch:
        batch.add_column(sa.Column("version_number", sa.Integer(), nullable=True))
        batch.alter_column(
            "status",
            existing_type=sa.String(30),
            existing_nullable=False,
            server_default="pending",
        )
        # 0012 limited the status to the old vocabulary; "assigned" is
        # "pending" now, and a new assignment failed the check on PostgreSQL.
        batch.drop_constraint("ck_reviewer_assignment_status", type_="check")
    op.execute("UPDATE reviewer_assignments SET status = 'pending' WHERE status = 'assigned'")
    with op.batch_alter_table("reviewer_assignments") as batch:
        batch.create_check_constraint(
            "ck_reviewer_assignment_status",
            "status IN ('pending','in_progress','completed','overdue')",
        )
    op.execute(
        "UPDATE reviewer_assignments SET version_number = "
        "(SELECT current_version FROM papers WHERE papers.id = reviewer_assignments.paper_id)"
    )

    with op.batch_alter_table("paper_reviews") as batch:
        batch.add_column(sa.Column("version_number", sa.Integer(), nullable=True))
        for name in _NEW_CRITERIA:
            batch.add_column(sa.Column(f"score_{name}", sa.Float(), nullable=True))
        for name in _ALL_CRITERIA:
            batch.add_column(sa.Column(f"comment_{name}", sa.Text(), nullable=True))
        batch.add_column(sa.Column("revision_notes", sa.Text(), nullable=True))
    op.execute(
        "UPDATE paper_reviews SET score_implementation = score_methodology, "
        "score_language = score_presentation, version_number = "
        "(SELECT current_version FROM papers WHERE papers.id = paper_reviews.paper_id)"
    )
    with op.batch_alter_table("paper_reviews") as batch:
        batch.drop_column("score_methodology")
        batch.drop_column("score_presentation")
        batch.drop_column("score_originality")


def downgrade() -> None:
    with op.batch_alter_table("paper_reviews") as batch:
        batch.add_column(sa.Column("score_methodology", sa.Float(), nullable=True))
        batch.add_column(sa.Column("score_presentation", sa.Float(), nullable=True))
        batch.add_column(sa.Column("score_originality", sa.Float(), nullable=True))
    op.execute(
        "UPDATE paper_reviews SET score_methodology = score_implementation, "
        "score_presentation = score_language"
    )
    with op.batch_alter_table("paper_reviews") as batch:
        batch.drop_column("revision_notes")
        for name in _ALL_CRITERIA:
            batch.drop_column(f"comment_{name}")
        for name in _NEW_CRITERIA:
            batch.drop_column(f"score_{name}")
        batch.drop_column("version_number")

    with op.batch_alter_table("reviewer_assignments") as batch:
        batch.drop_constraint("ck_reviewer_assignment_status", type_="check")
    op.execute("UPDATE reviewer_assignments SET status = 'assigned' WHERE status = 'pending'")
    op.execute("UPDATE reviewer_assignments SET status = 'assigned' WHERE status = 'in_progress'")
    with op.batch_alter_table("reviewer_assignments") as batch:
        batch.create_check_constraint(
            "ck_reviewer_assignment_status",
            "status IN ('assigned','in_progress','completed','overdue')",
        )
        batch.drop_column("version_number")
        batch.alter_column(
            "status",
            existing_type=sa.String(30),
            existing_nullable=False,
            server_default="assigned",
        )

    # papers.file_name already mirrors the latest version. Files of versions > 1
    # stay on disk under papers/<id>/v<n>/, where the old download route does
    # not look; move them up by hand if a downgrade must serve them.
    op.drop_index("ix_paper_versions_paper_id", table_name="paper_versions")
    op.drop_table("paper_versions")

    # Statuses unknown to the old code fall back to their nearest equivalent.
    op.execute("UPDATE papers SET status = 'submitted' WHERE status = 'resubmitted'")
    op.execute("UPDATE papers SET status = 'rejected' WHERE status = 'disqualified_ai'")
    with op.batch_alter_table("papers") as batch:
        batch.drop_constraint("uq_paper_season_team", type_="unique")
        batch.drop_column("finalized_at")
        batch.drop_column("format_deduction_reason")
        batch.drop_column("format_deduction")
        batch.drop_column("current_version")
