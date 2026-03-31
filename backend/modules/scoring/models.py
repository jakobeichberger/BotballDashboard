import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text, func
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class ScoringSchema(Base):
    """Defines which fields are scored and their multipliers for a season/level."""
    __tablename__ = "scoring_schemas"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    season_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False, index=True
    )
    competition_level_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("competition_levels.id"), nullable=True
    )
    fields: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Match(Base):
    __tablename__ = "matches"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    season_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False, index=True
    )
    phase_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("season_phases.id", ondelete="SET NULL"), nullable=True, index=True
    )
    team_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True
    )
    competition_level_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("competition_levels.id"), nullable=True
    )
    round_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    table_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raw_scores: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    total_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    is_disqualified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    yellow_card: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    red_card: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    entered_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    confirmed_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Ranking(Base):
    """Computed ranking cache – recalculated after each score entry."""
    __tablename__ = "rankings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    season_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False, index=True
    )
    phase_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("season_phases.id"), nullable=True, index=True
    )
    competition_level_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("competition_levels.id"), nullable=True
    )
    team_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False
    )
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    seed_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    best_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    average_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    rounds_played: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
