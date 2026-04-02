import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class Paper(Base):
    __tablename__ = "papers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    season_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False, index=True
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
    )  # draft | submitted | under_review | accepted | rejected | revision_requested
    file_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    submitted_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # Final numeric score (0-1) and rank set by admins after review
    final_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    paper_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
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


class ReviewerAssignment(Base):
    __tablename__ = "reviewer_assignments"

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
    assigned_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)

    paper: Mapped[Paper] = relationship(Paper, back_populates="assignments")


class PaperReview(Base):
    __tablename__ = "paper_reviews"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    paper_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("papers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    reviewer_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # Criteria scores (0-10 each)
    score_content: Mapped[float | None] = mapped_column(Float, nullable=True)
    score_methodology: Mapped[float | None] = mapped_column(Float, nullable=True)
    score_presentation: Mapped[float | None] = mapped_column(Float, nullable=True)
    score_originality: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    comments: Mapped[str | None] = mapped_column(Text, nullable=True)
    private_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommendation: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # accept | reject | revision_minor | revision_major
    is_submitted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    paper: Mapped[Paper] = relationship(Paper, back_populates="reviews")
