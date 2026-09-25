"""
Models for extended competition scoring:
  - DEResult: Double Elimination bracket results
  - AerialResult: Aerial drone competition runs
  - DocumentationScore: Documentation evaluation (P1/P2/P3 + Onsite)
  - JBCResult: Junior Botball Challenge – points for solved challenges
  - ResultRevision: append-only audit trail for the tables above
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
    """Aerial competition results for one team: its scoring runs in order.

    ``runs`` is a list (ECER 2026: six runs, the best three count); an entry
    may be null for a run not flown yet. How many runs count is configured on
    the category (SeasonCategory.counted_runs) or by the formula set.
    """

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
    runs: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    # aerial_score of the category's formula set (default: mean of the
    # counted runs), rank within the category
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
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
    # doc_score of the team's category formula set (ECER 2026: each period
    # normalised to the best team), else the game-review weighting
    # 0.2·P1 + 0.2·P2 + 0.2·P3 + 0.4·Onsite of the rubric maxima.
    doc_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    doc_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class JBCResult(Base):
    """Junior Botball Challenge: points for the challenges a team solved.

    ECER publishes "Points for Solved Challenges" and a rank. ``challenges``
    optionally lists what was solved ({key, points}); ``points`` is then their
    sum, otherwise it is entered directly.
    """

    __tablename__ = "jbc_results"
    __table_args__ = (UniqueConstraint("event_id", "team_id", name="uq_jbc_result_event_team"),)

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
    points: Mapped[float | None] = mapped_column(Float, nullable=True)
    challenges: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
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
    kind: Mapped[str] = mapped_column(String(20), nullable=False)  # de | aerial | doc | jbc
    previous_value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    new_value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    changed_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
