"""
Score Sheet Import – Pydantic Schemas
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Sub-schemas
# ---------------------------------------------------------------------------


class ScoringField(BaseModel):
    """One field in a scoring schema (matches existing ScoringSchema.fields format)."""

    key: str = Field(..., description="Machine-readable key, e.g. 'warehouse_floor_sorted_cubes'")
    label: str = Field(..., description="Human-readable label shown in the score form")
    multiplier: float = Field(default=1.0)
    max_value: float | None = None
    type: str = Field(default="count", description="'count' or 'boolean'")
    section: str | None = Field(None, description="Grouping header, e.g. 'Warehouse Floor'")
    notes: str | None = None


class ExtractedFieldCandidate(BaseModel):
    """
    A field candidate auto-detected by the OCR pipeline.
    The admin can accept, edit, or discard each candidate.
    """

    raw_text: str  # original text from OCR
    suggested_key: str  # auto-generated snake_case key
    suggested_label: str  # cleaned up label
    suggested_multiplier: float | None = None
    suggested_max_value: float | None = None
    confidence: float = Field(..., ge=0.0, le=1.0, description="OCR confidence 0–1")
    page: int = 1
    accepted: bool = False


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class ScoreSheetTemplateCreate(BaseModel):
    label: str
    year: int
    game_theme: str | None = None
    competition_level_id: UUID | None = None


class ScoreSheetTemplateResponse(BaseModel):
    id: UUID
    season_id: UUID
    competition_level_id: UUID | None
    label: str
    year: int
    game_theme: str | None
    is_active: bool
    file_name: str
    file_size_bytes: int | None
    ocr_status: str  # pending | processing | done | failed
    extracted_fields: list[ExtractedFieldCandidate] | None
    confirmed_fields: list[ScoringField] | None
    uploaded_by: UUID
    uploaded_at: datetime
    confirmed_by: UUID | None
    confirmed_at: datetime | None

    model_config = {"from_attributes": True}


class ScoreSheetTemplateListItem(BaseModel):
    """Lightweight version for list views."""

    id: UUID
    label: str
    year: int
    game_theme: str | None
    is_active: bool
    file_name: str
    ocr_status: str
    confirmed_fields_count: int | None = None
    uploaded_at: datetime

    model_config = {"from_attributes": True}


class ConfirmFieldsRequest(BaseModel):
    """Admin confirms (and optionally edits) the extracted fields to become the active schema."""

    fields: list[ScoringField]
    apply_to_schema: bool = Field(
        default=True,
        description="If true, immediately update the ScoringSchema for this season/level",
    )


class SetActiveRequest(BaseModel):
    sheet_id: UUID
