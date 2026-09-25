import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


# Paper lifecycle. "resubmitted" is a revised version handed in after
# revision_requested; "disqualified_ai" is the organizers' verdict on AI misuse
# (score 0, no further revision).
PAPER_STATUSES = (
    "draft",
    "submitted",
    "under_review",
    "revision_requested",
    "resubmitted",
    "accepted",
    "rejected",
    "disqualified_ai",
)
# Statuses in which the team may upload a new PDF version and (re)submit.
EDITABLE_STATUSES = frozenset({"draft", "revision_requested"})
# Statuses in which assigned reviewers may work on their review.
REVIEWABLE_STATUSES = frozenset({"submitted", "resubmitted", "under_review"})
# Statuses that close a review round: its submitted feedback becomes visible to
# the team.
DECIDED_STATUSES = frozenset({"accepted", "rejected", "revision_requested", "disqualified_ai"})

# The five review criteria of the spec (module 06), each scored 0-10 with an
# optional comment: concept/design, implementation, results/conclusion,
# language, formal requirements (IEEE format, length).
REVIEW_CRITERIA = ("content", "implementation", "results", "language", "format")


class Paper(Base):
    __tablename__ = "papers"
    # One official paper per team and season: the overall ranking reads
    # final_score per (season, team); revisions are versions of the same row.
    __table_args__ = (UniqueConstraint("season_id", "team_id", name="uq_paper_season_team"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    season_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("events.id", ondelete="CASCADE"), nullable=True, index=True
    )
    team_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    abstract: Mapped[str | None] = mapped_column(Text, nullable=True)
    competition_level_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("competition_levels.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="draft"
    )  # one of PAPER_STATUSES
    # Mirror of the latest PaperVersion, kept for list views and old clients.
    file_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    submitted_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    # Review round: bumped on every revision_requested.
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # Number of the latest uploaded PDF (PaperVersion.version_number).
    current_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Final numeric score (0-1) and rank set by admins after review
    final_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    paper_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Format violations: points on the 0-100 paper scale that finalize_paper
    # subtracts from the reviewers' average.
    format_deduction: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    format_deduction_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Set by finalize_paper; locks the current round's reviews.
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    reviews: Mapped[list["PaperReview"]] = relationship(
        "PaperReview", back_populates="paper", cascade="all, delete-orphan"
    )
    assignments: Mapped[list["ReviewerAssignment"]] = relationship(
        "ReviewerAssignment", back_populates="paper", cascade="all, delete-orphan"
    )
    versions: Mapped[list["PaperVersion"]] = relationship(
        "PaperVersion",
        back_populates="paper",
        cascade="all, delete-orphan",
        order_by="PaperVersion.version_number",
    )


class PaperVersion(Base):
    """One uploaded PDF. Every upload gets its own row and file; nothing is
    overwritten, so a review always refers to the exact file it judged."""

    __tablename__ = "paper_versions"
    __table_args__ = (
        UniqueConstraint("paper_id", "version_number", name="uq_paper_version_number"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    paper_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("papers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    # Review round the version was uploaded in.
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Relative to settings.upload_dir.
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    uploaded_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # Set when this version is handed in for review.
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    paper: Mapped[Paper] = relationship(Paper, back_populates="versions")


class ReviewerAssignment(Base):
    __tablename__ = "reviewer_assignments"
    __table_args__ = (
        UniqueConstraint("paper_id", "reviewer_id", name="uq_reviewer_assignment_paper_reviewer"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    paper_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("papers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    reviewer_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    assigned_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # pending | in_progress | completed | overdue. Reset to pending whenever a
    # revised version is resubmitted.
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    # The PDF version the reviewer is asked to judge.
    version_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reminder_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    paper: Mapped[Paper] = relationship(Paper, back_populates="assignments")


class PaperReview(Base):
    __tablename__ = "paper_reviews"
    __table_args__ = (
        UniqueConstraint(
            "paper_id",
            "reviewer_id",
            "revision_number",
            name="uq_paper_review_revision",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    paper_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("papers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    reviewer_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # The PDF version this review judges (PaperVersion.version_number).
    version_number: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Criterion scores (0-10 each, see REVIEW_CRITERIA), each with a comment.
    score_content: Mapped[float | None] = mapped_column(Float, nullable=True)
    score_implementation: Mapped[float | None] = mapped_column(Float, nullable=True)
    score_results: Mapped[float | None] = mapped_column(Float, nullable=True)
    score_language: Mapped[float | None] = mapped_column(Float, nullable=True)
    score_format: Mapped[float | None] = mapped_column(Float, nullable=True)
    comment_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    comment_implementation: Mapped[str | None] = mapped_column(Text, nullable=True)
    comment_results: Mapped[str | None] = mapped_column(Text, nullable=True)
    comment_language: Mapped[str | None] = mapped_column(Text, nullable=True)
    comment_format: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Mean of the criterion scores (0-10).
    total_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    comments: Mapped[str | None] = mapped_column(Text, nullable=True)
    # What the team concretely has to change for the next version.
    revision_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    private_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommendation: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # accept | reject | revision_minor | revision_major
    is_submitted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    paper: Mapped[Paper] = relationship(Paper, back_populates="reviews")


class PaperStatusHistory(Base):
    __tablename__ = "paper_status_history"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    paper_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("papers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    from_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    to_status: Mapped[str] = mapped_column(String(50), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    changed_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"))
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# Deadline types of module 06. Official ones come from the organizer's call
# for papers (KIPR/PRIA), internal ones are our own buffer for the review.
OFFICIAL_DEADLINE_TYPES = ("official_submission", "official_final")
INTERNAL_DEADLINE_TYPES = (
    "internal_draft",
    "internal_review",
    "internal_revision",
    "internal_final",
)
DEADLINE_TYPES = OFFICIAL_DEADLINE_TYPES + INTERNAL_DEADLINE_TYPES


class PaperDeadline(Base):
    """A dated paper deadline of a season.

    Official deadlines with ``is_hard_block`` lock uploads once they passed
    (organizers can still override); internal deadlines only warn. Teams (or,
    for internal_review, reviewers) are reminded 7, 3 and 1 day(s) before.
    """

    __tablename__ = "paper_deadlines"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    season_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False, index=True
    )
    deadline_type: Mapped[str] = mapped_column(String(30), nullable=False)
    # A calendar day, like Season.paper_submission_deadline: "15 March" means
    # the end of that day in the event's timezone.
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_hard_block: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
