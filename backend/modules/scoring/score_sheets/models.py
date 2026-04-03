"""
Score Sheet Import – SQLAlchemy Models
"""
import uuid

from sqlalchemy import Column, String, Integer, Boolean, ForeignKey, Text, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from core.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class ScoreSheetTemplate(Base):
    """
    A PDF score sheet uploaded for a specific season + competition level.
    Stores the original PDF and the extracted field definitions.
    """
    __tablename__ = "score_sheet_templates"

    id = Column(String(36), primary_key=True, default=_uuid)

    # Which season and level this sheet belongs to
    season_id = Column(String(36), ForeignKey("seasons.id"), nullable=False)
    competition_level_id = Column(
        String(36), ForeignKey("competition_levels.id"), nullable=True
    )  # NULL = applies to all levels in the season

    # Display metadata
    label = Column(String(255), nullable=False)
    year = Column(Integer, nullable=False)
    game_theme = Column(String(255))
    is_active = Column(Boolean, default=True, nullable=False)

    # Stored file
    file_url = Column(Text, nullable=False)
    file_name = Column(String(255), nullable=False)
    file_size_bytes = Column(Integer)

    # OCR / extraction results
    raw_text = Column(Text)
    extracted_fields = Column(JSONB)
    confirmed_fields = Column(JSONB)

    # Status of the OCR pipeline
    ocr_status = Column(String(30), default="pending")  # pending | processing | done | failed
    ocr_error = Column(Text)

    # Audit
    uploaded_by = Column(String(36), ForeignKey("users.id"), nullable=False)
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())
    confirmed_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    confirmed_at = Column(DateTime(timezone=True))

    # Relationships
    season = relationship("Season", back_populates="score_sheet_templates")
    competition_level = relationship("CompetitionLevel")
    uploader = relationship("User", foreign_keys=[uploaded_by])
    confirmer = relationship("User", foreign_keys=[confirmed_by])
