from datetime import datetime
from pydantic import BaseModel


class PrinterCreate(BaseModel):
    name: str
    model: str | None = None
    printer_type: str = "bambu"
    api_url: str | None = None
    api_key: str | None = None  # plain text – will be encrypted on save
    notes: str | None = None


class PrinterUpdate(BaseModel):
    name: str | None = None
    model: str | None = None
    api_url: str | None = None
    api_key: str | None = None
    is_active: bool | None = None
    notes: str | None = None


class PrinterResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    name: str
    model: str | None
    printer_type: str
    api_url: str | None
    is_active: bool
    is_online: bool
    last_seen: datetime | None
    notes: str | None
    # api_key_encrypted never returned


class PrintJobCreate(BaseModel):
    team_id: str
    season_id: str
    file_name: str
    material: str = "PLA"
    color: str | None = None
    estimated_grams: float | None = None
    estimated_minutes: int | None = None
    notes: str | None = None


class PrintJobUpdate(BaseModel):
    printer_id: str | None = None
    status: str | None = None
    actual_grams: float | None = None
    actual_minutes: int | None = None
    notes: str | None = None
    priority: int | None = None


class PrintJobResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    printer_id: str | None
    team_id: str
    season_id: str
    submitted_by: str | None
    file_name: str
    material: str
    color: str | None
    estimated_grams: float | None
    actual_grams: float | None
    estimated_minutes: int | None
    actual_minutes: int | None
    status: str
    priority: int
    notes: str | None
    approved_by: str | None
    approved_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime


class QuotaResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    team_id: str
    season_id: str
    max_parts: int
    soft_limit_parts: int
    max_grams: float | None
    used_parts: int
    used_grams: float
    notes: str | None


class FilamentSpoolCreate(BaseModel):
    printer_id: str | None = None
    material: str = "PLA"
    color: str | None = None
    brand: str | None = None
    initial_grams: float = 1000.0


class FilamentSpoolResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    printer_id: str | None
    material: str
    color: str | None
    brand: str | None
    initial_grams: float
    remaining_grams: float
    is_active: bool
    created_at: datetime
