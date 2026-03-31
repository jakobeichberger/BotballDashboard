import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class Printer(Base):
    __tablename__ = "printers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    model: Mapped[str | None] = mapped_column(String(255), nullable=True)  # e.g. "Bambu X1C", "Ender 3"
    printer_type: Mapped[str] = mapped_column(String(50), nullable=False, default="bambu")  # bambu | octoprint | generic
    api_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    api_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)  # Fernet-encrypted
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_online: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    print_jobs: Mapped[list["PrintJob"]] = relationship(
        "PrintJob", back_populates="printer", cascade="all, delete-orphan"
    )


class PrintJob(Base):
    __tablename__ = "print_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    printer_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("printers.id", ondelete="SET NULL"), nullable=True, index=True
    )
    team_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True
    )
    season_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False, index=True
    )
    submitted_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    material: Mapped[str] = mapped_column(String(50), default="PLA", nullable=False)  # PLA | PETG
    color: Mapped[str | None] = mapped_column(String(100), nullable=True)
    estimated_grams: Mapped[float | None] = mapped_column(Float, nullable=True)
    actual_grams: Mapped[float | None] = mapped_column(Float, nullable=True)
    estimated_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actual_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False)
    # pending | approved | queued | printing | completed | failed | cancelled
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    printer: Mapped[Printer | None] = relationship(Printer, back_populates="print_jobs")


class TeamSeasonPrintQuota(Base):
    __tablename__ = "team_season_print_quotas"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    team_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True
    )
    season_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False, index=True
    )
    max_parts: Mapped[int] = mapped_column(Integer, nullable=False, default=4)
    soft_limit_parts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    max_grams: Mapped[float | None] = mapped_column(Float, nullable=True)
    used_parts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    used_grams: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class FilamentSpool(Base):
    __tablename__ = "filament_spools"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    printer_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("printers.id", ondelete="SET NULL"), nullable=True
    )
    material: Mapped[str] = mapped_column(String(50), nullable=False, default="PLA")
    color: Mapped[str | None] = mapped_column(String(100), nullable=True)
    brand: Mapped[str | None] = mapped_column(String(100), nullable=True)
    initial_grams: Mapped[float] = mapped_column(Float, nullable=False, default=1000.0)
    remaining_grams: Mapped[float] = mapped_column(Float, nullable=False, default=1000.0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
