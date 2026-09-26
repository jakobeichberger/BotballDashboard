import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
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
    from modules.scoring.score_sheets.models import ScoreSheetTemplate


def _uuid() -> str:
    return str(uuid.uuid4())


SEASON_STATUSES = ("draft", "active", "finished", "archived")


def _initial_status(context) -> str:
    """A season created as active starts in the "active" state, others as drafts."""
    return "active" if context.get_current_parameters().get("is_active") else "draft"


class Season(Base):
    __tablename__ = "seasons"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    game_theme: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Lifecycle: draft | active | finished | archived. "active" mirrors is_active
    # (exactly one season); "archived" makes all of the season's data read-only
    # (see modules.seasons.lifecycle).
    status: Mapped[str] = mapped_column(
        String(20), default=_initial_status, server_default="draft", nullable=False, index=True
    )
    registration_open: Mapped[date | None] = mapped_column(Date, nullable=True)
    registration_close: Mapped[date | None] = mapped_column(Date, nullable=True)
    event_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    event_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    paper_submission_deadline: Mapped[date | None] = mapped_column(Date, nullable=True)
    print_submission_deadline: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Competition module toggles ─────────────────────────────────────────
    use_seeding: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    use_double_elimination: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    use_paper_scoring: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    use_documentation_scoring: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    use_aerial: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Active team categories in this season (keys of the category registry,
    # see SeasonCategory / modules.seasons.categories)
    active_categories: Mapped[list] = mapped_column(
        JSON, default=lambda: ["botball"], nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    phases: Mapped[list[SeasonPhase]] = relationship(
        "SeasonPhase",
        back_populates="season",
        cascade="all, delete-orphan",
        order_by="SeasonPhase.sort_order",
    )
    score_sheet_templates: Mapped[list[ScoreSheetTemplate]] = relationship(
        "ScoreSheetTemplate", back_populates="season", cascade="all, delete-orphan"
    )


class SeasonPhase(Base):
    __tablename__ = "season_phases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    season_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    phase_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # seeding | double_seeding | elimination | final
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    rounds: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    season: Mapped[Season] = relationship(Season, back_populates="phases")


class CompetitionLevel(Base):
    __tablename__ = "competition_levels"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(100), nullable=False)  # ECER | GCER | Junior
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # 1 = ECER, 2 = GCER, …; "order" is reserved in SQL, hence the column name.
    order: Mapped[int] = mapped_column("level_order", Integer, default=0, nullable=False)
    # GCER qualifies from ECER: teams need a TeamQualification for this level
    # (in the event's season) before they can be registered for it.
    qualifies_from_level_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("competition_levels.id", ondelete="SET NULL"), nullable=True
    )


class SeasonEvent(Base):
    """A dated deadline or event attached to a season (submission deadlines,
    kickoffs, competition days, …)."""

    __tablename__ = "season_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    season_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    event_type: Mapped[str] = mapped_column(
        String(20), default="deadline", nullable=False
    )  # deadline | event
    event_date: Mapped[date] = mapped_column(Date, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SeasonCategory(Base):
    """One competition category of a season (Botball, ECER Open, Aerial Junior, …).

    Team registrations, formula sets, bracket weights and rankings refer to a
    category by its ``key``. A season without rows uses the defaults of
    ``modules.seasons.categories``; ``kind`` says which results a category
    has (seeding/DE/documentation, aerial runs, JBC points) and which shipped
    formula set it falls back to.
    """

    __tablename__ = "season_categories"
    __table_args__ = (UniqueConstraint("season_id", "key", name="uq_season_category_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    season_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False, index=True
    )
    key: Mapped[str] = mapped_column(String(20), nullable=False)
    label_de: Mapped[str] = mapped_column(String(100), nullable=False)
    label_en: Mapped[str] = mapped_column(String(100), nullable=False)
    # botball | open | aerial | jbc | custom
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default="custom")
    # Formula preset used while the season stores no formulas for the category.
    formula_preset: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # Aerial: run columns offered for entry and how many of the best count
    # (None: all runs).
    run_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    counted_runs: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # GCER: rank the overall score per DE bracket ("course"/tier) as well.
    rank_per_bracket: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
