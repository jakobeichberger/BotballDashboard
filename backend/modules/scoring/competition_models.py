"""
Models for extended competition scoring:
  - DEResult: Double Elimination bracket results
  - AerialResult: Aerial drone competition runs
  - DocumentationScore: Documentation evaluation (P1/P2/P3 + Onsite)
  - ResultRevision: append-only audit trail for the three tables above
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class DEResult(Base):
    """Double-Elimination bracket result for one team in one season."""

    __tablename__ = "de_results"
    __table_args__ = (UniqueConstraint("event_id", "team_id", name="uq_de_result_event_team"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    season_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True
    )
    team_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True
    )
    bracket: Mapped[str] = mapped_column(String(1), nullable=False)  # "A" | "B"
    de_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bracket_score: Mapped[float | None] = mapped_column(Float, nullable=True)  # 0-1 within bracket
    de_score: Mapped[float | None] = mapped_column(Float, nullable=True)  # final 0-1
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
    __table_args__ = (UniqueConstraint("event_id", "team_id", name="uq_aerial_result_event_team"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    season_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True
    )
    team_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True
    )
    run1: Mapped[float | None] = mapped_column(Float, nullable=True)
    run2: Mapped[float | None] = mapped_column(Float, nullable=True)
    run3: Mapped[float | None] = mapped_column(Float, nullable=True)
    run4: Mapped[float | None] = mapped_column(Float, nullable=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)  # mean of all runs
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
    __table_args__ = (UniqueConstraint("event_id", "team_id", name="uq_doc_score_event_team"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    season_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True
    )
    team_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True
    )
    part1: Mapped[float | None] = mapped_column(Float, nullable=True)  # 0-100
    part2: Mapped[float | None] = mapped_column(Float, nullable=True)
    part3: Mapped[float | None] = mapped_column(Float, nullable=True)
    onsite: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Regional formula 0.2·P1 + 0.2·P2 + 0.2·P3 + 0.4·Onsite (each /100),
    # missing parts count 0. Event-specific rules (ECER, GCER) are applied by
    # the formula engine; this column is the plain game-review value.
    doc_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    doc_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ResultRevision(Base):
    """One change to a DE, aerial or documentation result.

    The match scores have their own, richer ScoreRevision table; these three
    result kinds share this small generic one. `new_value` is NULL when a
    result was removed. team_id is a plain column (no FK) so the trail
    survives a team being deleted.
    """

    __tablename__ = "result_revisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    event_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True
    )
    team_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)  # de | aerial | doc
    previous_value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    new_value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    changed_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
