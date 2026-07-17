"""
Score Sheet Import – SQLAlchemy Models
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from core.database import Base

if TYPE_CHECKING:
    from modules.auth.models import User
    from modules.seasons.models import CompetitionLevel, Season

JSON_TYPE = JSON().with_variant(JSONB, "postgresql")


def _uuid() -> str:
    return str(uuid.uuid4())


class ScoreSheetTemplate(Base):
    """
    A PDF score sheet uploaded for a specific season + competition level.
    Stores the original PDF and the extracted field definitions.
    """

    __tablename__ = "score_sheet_templates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)

    # Which season and level this sheet belongs to
    season_id: Mapped[str] = mapped_column(String(36), ForeignKey("seasons.id"), nullable=False)
    competition_level_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("competition_levels.id"), nullable=True
    )  # NULL = applies to all levels in the season

    # Display metadata
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    game_theme: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Stored file
    file_url: Mapped[str] = mapped_column(Text, nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_size_bytes: Mapped[int | None] = mapped_column(Integer)

    # OCR / extraction results
    raw_text: Mapped[str | None] = mapped_column(Text)
    extracted_fields: Mapped[list[dict] | None] = mapped_column(JSON_TYPE)
    confirmed_fields: Mapped[list[dict] | None] = mapped_column(JSON_TYPE)

    # Status of the OCR pipeline
    ocr_status: Mapped[str] = mapped_column(String(30), default="pending")
    ocr_error: Mapped[str | None] = mapped_column(Text)

    # Audit
    uploaded_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    confirmed_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Relationships
    season: Mapped["Season"] = relationship("Season", back_populates="score_sheet_templates")
    competition_level: Mapped["CompetitionLevel | None"] = relationship("CompetitionLevel")
    uploader: Mapped["User"] = relationship("User", foreign_keys=[uploaded_by])
    confirmer: Mapped["User | None"] = relationship("User", foreign_keys=[confirmed_by])
