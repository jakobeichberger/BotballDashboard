from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class PrinterCreate(BaseModel):
    name: str
    model: str | None = None
    # generic = manually operated printer without an adapter (never polled)
    printer_type: Literal["bambu", "octoprint", "generic"] = "bambu"
    api_url: str | None = None
    device_id: str | None = None
    api_key: str | None = None  # plain text – will be encrypted on save
    notes: str | None = None


class PrinterUpdate(BaseModel):
    name: str | None = None
    model: str | None = None
    api_url: str | None = None
    device_id: str | None = None
    api_key: str | None = None
    is_active: bool | None = None
    notes: str | None = None


class PrinterPublicResponse(BaseModel):
    """Read-only printer status for mentors: no connection details."""

    model_config = {"from_attributes": True}

    id: str
    name: str
    model: str | None
    printer_type: str
    is_active: bool
    is_online: bool
    last_seen: datetime | None
    current_state: str | None = None
    status_message: str | None = None


class PrinterResponse(PrinterPublicResponse):
    # Only filled for printing:admin; mentors get the public subset above.
    api_url: str | None = None
    device_id: str | None = None
    notes: str | None = None
    # api_key_encrypted never returned


class PrintJobCreate(BaseModel):
    team_id: str
    season_id: str
    event_id: str | None = None
    file_name: str
    material: str = "PLA"
    color: str | None = None
    estimated_grams: float | None = Field(default=None, ge=0)
    estimated_minutes: int | None = Field(default=None, ge=0)
    notes: str | None = None
    # printing:admin only: submit although the team's hard limit is reached.
    quota_override: bool = False
    # robot parts count towards the 6-part limit; spares and jigs do not.
    purpose: Literal["robot", "spare", "jig"] = "robot"
    part_count: int = Field(default=1, ge=1, le=50)


class PrintJobUpdate(BaseModel):
    printer_id: str | None = None
    # "rejected" needs a reason and goes through PUT /jobs/{id}/reject.
    status: (
        Literal["pending", "approved", "queued", "printing", "completed", "failed", "cancelled"]
        | None
    ) = None
    spool_id: str | None = None
    actual_grams: float | None = Field(default=None, ge=0)
    actual_minutes: int | None = Field(default=None, ge=0)
    notes: str | None = None
    priority: int | None = None
    purpose: Literal["robot", "spare", "jig"] | None = None
    part_count: int | None = Field(default=None, ge=1, le=50)
    # The STL was handed in with documentation Period 3.
    stl_submitted: bool | None = None
    # Retry a failed job although the team's hard limit is reached (audited).
    quota_override: bool | None = None


class PrintJobResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    printer_id: str | None
    team_id: str
    season_id: str
    event_id: str | None
    submitted_by: str | None
    file_name: str
    file_url: str | None = None
    file_size_bytes: int | None = None
    material: str
    color: str | None
    purpose: str = "robot"
    part_count: int = 1
    bbox_x_mm: float | None = None
    bbox_y_mm: float | None = None
    bbox_z_mm: float | None = None
    stl_submitted: bool = False
    # material_not_allowed | color_not_greyscale | exceeds_build_volume
    rule_warnings: list[str] = []
    estimated_grams: float | None
    actual_grams: float | None
    estimated_minutes: int | None
    actual_minutes: int | None
    status: str
    priority: int
    progress: float | None
    status_message: str | None
    remaining_seconds: int | None = None
    error_message: str | None = None
    rejection_reason: str | None = None
    quota_override: bool = False
    spool_id: str | None = None
    external_job_id: str | None
    last_polled_at: datetime | None
    notes: str | None
    approved_by: str | None
    approved_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime


class PrintJobCreateResponse(PrintJobResponse):
    # Set when the job takes the team past its soft limit (it is still accepted).
    quota_warning: str | None = None
    # Set when the team's 3D-print compliance checklist for the season is not
    # complete (the job is still accepted).
    compliance_warning: str | None = None


class RobotPartsSummary(BaseModel):
    """Printed robot parts of a team in a season against the game-review limit."""

    team_id: str
    season_id: str
    used: int
    limit: int
    over_limit: bool
    stl_missing: int


class PrintJobCancelResponse(PrintJobResponse):
    # sent | failed | not_applicable – whether a running print was also
    # aborted on the printer itself.
    printer_cancel: str = "not_applicable"
    printer_message: str | None = None


class PrintJobReject(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)


class QuotaUpsert(BaseModel):
    team_id: str
    season_id: str
    # Quotas are per event; omitted means the season's default event.
    event_id: str | None = None
    max_parts: int | None = Field(default=None, ge=0)
    soft_limit_parts: int | None = Field(default=None, ge=0)
    max_grams: float | None = Field(default=None, ge=0)
    # max_grams=None means "leave unchanged"; this removes the gram limit.
    clear_max_grams: bool = False
    notes: str | None = None


class QuotaResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    team_id: str
    season_id: str
    event_id: str | None = None
    max_parts: int
    soft_limit_parts: int
    max_grams: float | None
    used_parts: int
    used_grams: float
    # Submitted but unfinished jobs; they count toward the hard limit too.
    open_parts: int = 0
    open_grams: float = 0.0
    notes: str | None
    team_name: str | None = None  # only in the per-event listing


class FilamentSpoolCreate(BaseModel):
    printer_id: str | None = None
    material: str = "PLA"
    color: str | None = None
    brand: str | None = None
    initial_grams: float = Field(default=1000.0, gt=0)


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
