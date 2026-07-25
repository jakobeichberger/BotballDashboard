import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base

if TYPE_CHECKING:
    from modules.teams.models import Team


def _uuid() -> str:
    return str(uuid.uuid4())


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (UniqueConstraint("slug", name="uq_events_slug"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    season_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False, default="regional")
    timezone: Mapped[str] = mapped_column(String(80), nullable=False, default="Europe/Vienna")
    venue: Mapped[str | None] = mapped_column(String(255), nullable=True)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="draft")
    active_modules: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=lambda: ["seeding"]
    )
    public_scoreboard: Mapped[bool] = mapped_column(default=False, nullable=False)
    public_schedule: Mapped[bool] = mapped_column(default=False, nullable=False)
    public_results: Mapped[bool] = mapped_column(default=False, nullable=False)
    public_announcements: Mapped[bool] = mapped_column(default=False, nullable=False)
    table_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    registrations: Mapped[list["EventRegistration"]] = relationship(
        "EventRegistration", back_populates="event", cascade="all, delete-orphan"
    )
    phases: Mapped[list["EventPhase"]] = relationship(
        "EventPhase",
        back_populates="event",
        cascade="all, delete-orphan",
        order_by="EventPhase.sort_order",
    )


class EventRegistration(Base):
    __tablename__ = "event_registrations"
    __table_args__ = (
        UniqueConstraint("event_id", "team_id", name="uq_event_registration_event_team"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    event_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True
    )
    team_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True
    )
    competition_level_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("competition_levels.id"), nullable=True
    )
    category: Mapped[str] = mapped_column(String(30), nullable=False, default="botball")
    seed_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    checked_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    event: Mapped[Event] = relationship(Event, back_populates="registrations")
    team: Mapped["Team"] = relationship("Team")

    @property
    def team_name(self) -> str:
        return self.team.name

    @property
    def team_number(self) -> str | None:
        return self.team.team_number


class EventPhase(Base):
    __tablename__ = "event_phases"
    __table_args__ = (UniqueConstraint("event_id", "sort_order", name="uq_event_phase_sort_order"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    event_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    phase_type: Mapped[str] = mapped_column(String(40), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="draft")
    rounds: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    settings: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    event: Mapped[Event] = relationship(Event, back_populates="phases")
    scheduled_matches: Mapped[list["ScheduledMatch"]] = relationship(
        "ScheduledMatch", back_populates="phase", cascade="all, delete-orphan"
    )


class ScheduledMatch(Base):
    __tablename__ = "scheduled_matches"
    __table_args__ = (UniqueConstraint("event_id", "code", name="uq_scheduled_match_event_code"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    event_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True
    )
    phase_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("event_phases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    round_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    table_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="scheduled")
    bracket: Mapped[str | None] = mapped_column(String(30), nullable=True)
    next_winner_match_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("scheduled_matches.id", ondelete="SET NULL"), nullable=True
    )
    next_loser_match_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("scheduled_matches.id", ondelete="SET NULL"), nullable=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    phase: Mapped[EventPhase] = relationship(EventPhase, back_populates="scheduled_matches")
    participants: Mapped[list["MatchParticipant"]] = relationship(
        "MatchParticipant", back_populates="scheduled_match", cascade="all, delete-orphan"
    )


class MatchParticipant(Base):
    __tablename__ = "match_participants"
    __table_args__ = (
        UniqueConstraint("scheduled_match_id", "position", name="uq_match_participant_position"),
        UniqueConstraint("scheduled_match_id", "team_id", name="uq_match_participant_team"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    scheduled_match_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("scheduled_matches.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    team_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("teams.id", ondelete="CASCADE"), nullable=True, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    side: Mapped[str | None] = mapped_column(String(20), nullable=True)
    result: Mapped[str | None] = mapped_column(String(20), nullable=True)
    score: Mapped[float | None] = mapped_column(nullable=True)

    scheduled_match: Mapped[ScheduledMatch] = relationship(
        ScheduledMatch, back_populates="participants"
    )
    team: Mapped["Team | None"] = relationship("Team")

    @property
    def team_name(self) -> str | None:
        return self.team.name if self.team else None

    @property
    def team_number(self) -> str | None:
        return self.team.team_number if self.team else None
