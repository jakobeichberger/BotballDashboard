import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    false,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

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
    event_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("events.id", ondelete="CASCADE"), nullable=True, index=True
    )
    competition_level_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("competition_levels.id"), nullable=True
    )
    fields: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    # Structured sheet (sections, area multipliers, either-or, sides A/B – see
    # modules.scoring.sheet). When set it is authoritative and `fields` holds
    # the flattened inputs; legacy flat schemas leave it NULL.
    definition: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Match(Base):
    __tablename__ = "matches"
    __table_args__ = (
        # A team's runs at an event: ranking rebuilds, dashboards, history.
        Index("ix_matches_event_team", "event_id", "team_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    season_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True
    )
    scheduled_match_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("scheduled_matches.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    phase_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("season_phases.id", ondelete="SET NULL"), nullable=True, index=True
    )
    event_phase_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("event_phases.id", ondelete="SET NULL"), nullable=True, index=True
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
    schema_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    total_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    # total_score = 0 if round_lost else sheet_score + bonus_score
    sheet_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    # 25 % of the opponent's score when the opponent was intentionally touching
    # this team's side at the end of a head-to-head match.
    bonus_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    # This team intentionally touched the opponent's side at the end of the game.
    end_contact: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # "Lose the round" (never left the start box / motors still running): the
    # round scores 0 but, unlike a DQ, still counts as a played round.
    round_lost: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    round_lost_reason: Mapped[str | None] = mapped_column(String(40), nullable=True)
    # Juror-entered tie-breaker values, keyed by criterion key.
    tiebreak_values: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # Referee checklist ticked before confirming: {item_key: bool}
    checklist: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    is_disqualified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_practice: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    yellow_card: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    red_card: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    idempotency_key: Mapped[str | None] = mapped_column(String(100), nullable=True, unique=True)
    entered_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    confirmed_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
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
    __table_args__ = (
        UniqueConstraint(
            "event_id",
            "team_id",
            "phase_id",
            "competition_level_id",
            name="uq_ranking_event_team_phase_level",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    season_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True
    )
    phase_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("season_phases.id"), nullable=True, index=True
    )
    event_phase_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("event_phases.id", ondelete="SET NULL"), nullable=True, index=True
    )
    competition_level_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("competition_levels.id"), nullable=True
    )
    team_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False
    )
    # NULL when the team is disqualified (red card): it keeps its row, so the
    # scores stay visible, but it takes no place in the ranking.
    rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Registration category (botball / open / …) the rank is computed within —
    # Botball and Open teams are ranked separately.
    category: Mapped[str | None] = mapped_column(String(30), nullable=True)
    disqualified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    seed_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    best_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    average_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    rounds_played: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Label of the tie-breaker that placed this team against an equal seed score.
    tiebreaker: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ScoreRevision(Base):
    """Append-only history for every official score mutation.

    The history outlives the match: deleting a match writes a final "deleted"
    revision and detaches the rows (match_id → NULL) instead of cascading, and
    `match_ref` keeps the original match id so the trail stays queryable.
    """

    __tablename__ = "score_revisions"
    __table_args__ = (
        UniqueConstraint("match_id", "revision", name="uq_score_revision_match_revision"),
        # The event's audit trail, newest first.
        Index("ix_score_revisions_event_created", "event_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    match_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("matches.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Plain copies (no FK), so they survive the match being deleted.
    match_ref: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    team_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    # Copy of Match.is_practice: practice history is only for the team itself
    # and organizers (modules.scoring.visibility). NULL for rows written before
    # migration 0031 whose match no longer exists.
    is_practice: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    event_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    previous_raw_scores: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    new_raw_scores: Mapped[dict] = mapped_column(JSON, nullable=False)
    previous_total_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    new_total_score: Mapped[float] = mapped_column(Float, nullable=False)
    previous_value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    new_value: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    changed_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
