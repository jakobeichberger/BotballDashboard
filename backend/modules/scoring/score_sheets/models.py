"""
Score Sheet Import – SQLAlchemy Models
"""

from sqlalchemy import Column, String, Integer, Boolean, ForeignKey, Text, DateTime
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid

from core.database import Base


class ScoreSheetTemplate(Base):
    """
    A PDF score sheet uploaded for a specific season + competition level.
    Stores the original PDF and the extracted field definitions.
    """
    __tablename__ = "score_sheet_templates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Which season and level this sheet belongs to
    season_id = Column(UUID(as_uuid=True), ForeignKey("seasons.id"), nullable=False)
    competition_level_id = Column(
        UUID(as_uuid=True), ForeignKey("competition_levels.id"), nullable=True
    )  # NULL = applies to all levels in the season

    # Display metadata
    label = Column(String(255), nullable=False)          # e.g. "ECER 2026 Official Sheet"
    year = Column(Integer, nullable=False)
    game_theme = Column(String(255))                      # e.g. "Warehouse & Logistics"
    is_active = Column(Boolean, default=True, nullable=False)  # which sheet is currently used

    # Stored file
    file_url = Column(Text, nullable=False)               # path on server / object storage key
    file_name = Column(String(255), nullable=False)
    file_size_bytes = Column(Integer)

    # OCR / extraction results
    raw_text = Column(Text)                               # full pdftotext output
    extracted_fields = Column(JSONB)                      # auto-detected field candidates
    confirmed_fields = Column(JSONB)                      # admin-confirmed schema (array of ScoringField)

    # Status of the OCR pipeline
    ocr_status = Column(
        String(30), default="pending"
    )  # pending | processing | done | failed
    ocr_error = Column(Text)

    # Audit
    uploaded_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())
    confirmed_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    confirmed_at = Column(DateTime(timezone=True))

    # Relationships
    season = relationship("Season", back_populates="score_sheet_templates")
    competition_level = relationship("CompetitionLevel")
    uploader = relationship("User", foreign_keys=[uploaded_by])
    confirmer = relationship("User", foreign_keys=[confirmed_by])
