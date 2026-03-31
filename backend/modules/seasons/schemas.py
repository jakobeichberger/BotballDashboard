from datetime import datetime, date
from pydantic import BaseModel


class SeasonPhaseCreate(BaseModel):
    name: str
    phase_type: str
    sort_order: int = 0
    rounds: int = 3
    start_date: date | None = None
    end_date: date | None = None


class SeasonPhaseResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    name: str
    phase_type: str
    sort_order: int
    is_active: bool
    rounds: int
    start_date: date | None
    end_date: date | None


class SeasonCreate(BaseModel):
    name: str
    year: int
    game_theme: str | None = None
    registration_open: date | None = None
    registration_close: date | None = None
    event_start: date | None = None
    event_end: date | None = None
    paper_submission_deadline: date | None = None
    print_submission_deadline: date | None = None
    notes: str | None = None
    phases: list[SeasonPhaseCreate] = []


class SeasonUpdate(BaseModel):
    name: str | None = None
    game_theme: str | None = None
    is_active: bool | None = None
    registration_open: date | None = None
    registration_close: date | None = None
    event_start: date | None = None
    event_end: date | None = None
    paper_submission_deadline: date | None = None
    print_submission_deadline: date | None = None
    notes: str | None = None


class SeasonResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    name: str
    year: int
    game_theme: str | None
    is_active: bool
    registration_open: date | None
    registration_close: date | None
    event_start: date | None
    event_end: date | None
    paper_submission_deadline: date | None
    print_submission_deadline: date | None
    notes: str | None
    created_at: datetime
    phases: list[SeasonPhaseResponse]


class SeasonListItem(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    name: str
    year: int
    game_theme: str | None
    is_active: bool
    event_start: date | None
    event_end: date | None


class CompetitionLevelResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    name: str
    code: str
    description: str | None
    is_active: bool
