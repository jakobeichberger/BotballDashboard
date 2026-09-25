"""Season scoring rules, scouting, GCER qualification and parts challenges.

* ScoringRuleSet – per-season tie-breaker order, finals replay rule, the 25 %
  end-of-game-contact bonus and the referee checklist.
* ExternalTeam / ScoutingNote / ScoutingObservation – opponents that are not
  managed in the system, and what our teams observed about them at an event.
* TeamQualification – "qualified for the next level" (ECER → GCER), set
  manually by an admin.
* PartsChallenge – a challenge of the opponent's robot at a head-to-head match
  (game review "Challenges": the loser of the challenge is disqualified for the
  round).
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
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


class ScoringRuleSet(Base):
    __tablename__ = "scoring_rule_sets"
    __table_args__ = (UniqueConstraint("season_id", name="uq_scoring_rule_set_season"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    season_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Ordered criteria, see modules.scoring.tiebreak
    tiebreakers: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    # 2026: "In the finals tie breakers will not be used, the match is replayed".
    finals_replay: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    end_contact_bonus_percent: Mapped[float] = mapped_column(Float, nullable=False, default=25.0)
    # [{key, label, required}] – ticked by the juror before confirming a score
    referee_checklist: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    # Break equal seed scores with the tie-breakers. Off by default: the game
    # review applies tie-breakers to head-to-head rounds, and seeding ties
    # share a rank (ECER 2026 results: two teams on seeding rank 7).
    seeding_tiebreakers: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    # Rubric maxima of the documentation periods, {"p1": 100, "p2": 95, ...};
    # NULL means 100 each (see rules_service.DOC_MAX_DEFAULT).
    doc_max_points: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ExternalTeam(Base):
    __tablename__ = "external_teams"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    season_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    school: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="observed")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ScoutingNote(Base):
    """Free-text scouting notes. Owned by one of our teams (null: organizers)."""

    __tablename__ = "scouting_notes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    event_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True
    )
    external_team_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("external_teams.id", ondelete="CASCADE"), nullable=False, index=True
    )
    owner_team_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("teams.id", ondelete="CASCADE"), nullable=True, index=True
    )
    author_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    threat_level: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 1-5
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ScoutingObservation(Base):
    """A score we saw an external team make (seeding run, DE match, …)."""

    __tablename__ = "scouting_observations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    event_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True
    )
    external_team_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("external_teams.id", ondelete="CASCADE"), nullable=False, index=True
    )
    owner_team_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("teams.id", ondelete="CASCADE"), nullable=True, index=True
    )
    author_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    phase: Mapped[str] = mapped_column(String(30), nullable=False, default="seeding")
    round_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class TeamQualification(Base):
    __tablename__ = "team_qualifications"
    __table_args__ = (
        UniqueConstraint("season_id", "team_id", "level_id", name="uq_team_qualification"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    season_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False, index=True
    )
    team_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # The level the team may now take part in (e.g. GCER) …
    level_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("competition_levels.id", ondelete="CASCADE"), nullable=False
    )
    # … and the one it qualified from (e.g. ECER), with the event it happened at.
    from_level_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("competition_levels.id", ondelete="SET NULL"), nullable=True
    )
    source_event_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("events.id", ondelete="SET NULL"), nullable=True
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    qualified_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PartsChallenge(Base):
    __tablename__ = "parts_challenges"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    event_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True
    )
    scheduled_match_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("scheduled_matches.id", ondelete="SET NULL"), nullable=True
    )
    challenger_team_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False
    )
    challenged_team_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    # None while the head judge decides; True: challenged team DQ, False: challenger DQ
    upheld: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    ruling_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
