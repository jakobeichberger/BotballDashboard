"""
Models for extended competition scoring:
  - DEResult: Double Elimination bracket results
  - AerialResult: Aerial drone competition runs
  - DocumentationScore: Documentation evaluation (P1/P2/P3 + Onsite)
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class DEResult(Base):
    """Double-Elimination bracket result for one team in one season."""
    __tablename__ = "de_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    season_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False, index=True
    )
    team_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True
    )
    bracket: Mapped[str] = mapped_column(String(1), nullable=False)  # "A" | "B"
    de_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bracket_score: Mapped[float | None] = mapped_column(Float, nullable=True)  # 0-1 within bracket
    de_score: Mapped[float | None] = mapped_column(Float, nullable=True)       # final 0-1
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class AerialResult(Base):
    """Aerial competition results for one team – up to 4 timed/scored runs."""
    __tablename__ = "aerial_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    season_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False, index=True
    )
    team_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True
    )
    run1: Mapped[float | None] = mapped_column(Float, nullable=True)
    run2: Mapped[float | None] = mapped_column(Float, nullable=True)
    run3: Mapped[float | None] = mapped_column(Float, nullable=True)
    run4: Mapped[float | None] = mapped_column(Float, nullable=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)  # avg of best 2
    rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class DocumentationScore(Base):
    """Documentation evaluation (3 written parts + onsite) for one team."""
    __tablename__ = "documentation_scores"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    season_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False, index=True
    )
    team_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True
    )
    part1: Mapped[float | None] = mapped_column(Float, nullable=True)   # 0-100
    part2: Mapped[float | None] = mapped_column(Float, nullable=True)
    part3: Mapped[float | None] = mapped_column(Float, nullable=True)
    onsite: Mapped[float | None] = mapped_column(Float, nullable=True)
    doc_score: Mapped[float | None] = mapped_column(Float, nullable=True)  # avg(p1,p2,p3)/100
    doc_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
