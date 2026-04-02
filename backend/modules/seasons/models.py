import uuid
from datetime import datetime, date

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, JSON, String, Text, Integer, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class Season(Base):
    __tablename__ = "seasons"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    game_theme: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
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
    # Active team categories in this season: ["botball", "open", "aerial", "jbc"]
    active_categories: Mapped[list] = mapped_column(JSON, default=lambda: ["botball"], nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    phases: Mapped[list["SeasonPhase"]] = relationship(
        "SeasonPhase", back_populates="season", cascade="all, delete-orphan", order_by="SeasonPhase.sort_order"
    )


class SeasonPhase(Base):
    __tablename__ = "season_phases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    season_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    phase_type: Mapped[str] = mapped_column(String(50), nullable=False)  # seeding | double_seeding | elimination | final
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
