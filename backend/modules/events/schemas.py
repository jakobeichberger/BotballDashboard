from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

EventStatus = Literal["draft", "published", "live", "completed", "archived"]
PhaseType = Literal["seeding", "double_seeding", "double_elimination", "alliance", "final"]
PhaseStatus = Literal["draft", "scheduled", "live", "completed"]


def _validate_module_names(value: list[str]) -> list[str]:
    allowed = {"seeding", "double_elimination", "paper", "documentation", "aerial"}
    invalid = set(value) - allowed
    if invalid:
        raise ValueError(f"Unknown modules: {', '.join(sorted(invalid))}")
    return list(dict.fromkeys(value))


class EventCreate(BaseModel):
    season_id: str
    name: str = Field(min_length=2, max_length=255)
    slug: str = Field(min_length=2, max_length=120, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    event_type: str = Field(default="regional", max_length=40)
    timezone: str = Field(default="Europe/Vienna", max_length=80)
    venue: str | None = Field(default=None, max_length=255)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    status: EventStatus = "draft"
    active_modules: list[str] = Field(default_factory=lambda: ["seeding"])
    public_scoreboard: bool = False
    public_schedule: bool = False
    public_results: bool = False
    public_announcements: bool = False
    table_count: int = Field(default=1, ge=1, le=100)
    notes: str | None = None

    @field_validator("active_modules")
    @classmethod
    def validate_modules(cls, value: list[str]) -> list[str]:
        return _validate_module_names(value)

    @model_validator(mode="after")
    def validate_dates(self) -> "EventCreate":
        if self.starts_at and self.ends_at and self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be after starts_at")
        return self


class EventUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    slug: str | None = Field(
        default=None, min_length=2, max_length=120, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
    )
    event_type: str | None = Field(default=None, max_length=40)
    timezone: str | None = Field(default=None, max_length=80)
    venue: str | None = Field(default=None, max_length=255)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    status: EventStatus | None = None
    active_modules: list[str] | None = None
    public_scoreboard: bool | None = None
    public_schedule: bool | None = None
    public_results: bool | None = None
    public_announcements: bool | None = None
    table_count: int | None = Field(default=None, ge=1, le=100)
    notes: str | None = None

    @field_validator("active_modules")
    @classmethod
    def validate_modules(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return value
        return _validate_module_names(value)


class EventResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    season_id: str
    name: str
    slug: str
    event_type: str
    timezone: str
    venue: str | None
    starts_at: datetime | None
    ends_at: datetime | None
    status: str
    active_modules: list[str]
    public_scoreboard: bool
    public_schedule: bool
    public_results: bool
    public_announcements: bool
    table_count: int
    notes: str | None
    created_at: datetime
    updated_at: datetime


class EventPublicResponse(BaseModel):
    id: str
    season_id: str
    name: str
    slug: str
    event_type: str
    timezone: str
    venue: str | None
    starts_at: datetime | None
    ends_at: datetime | None
    status: str
    public_scoreboard: bool
    public_schedule: bool
    public_results: bool
    public_announcements: bool


class EventRegistrationCreate(BaseModel):
    team_id: str
    competition_level_id: str | None = None
    category: Literal["botball", "open", "aerial", "jbc"] = "botball"
    seed_number: int | None = Field(default=None, ge=1)
    notes: str | None = None


class EventRegistrationUpdate(BaseModel):
    competition_level_id: str | None = None
    category: Literal["botball", "open", "aerial", "jbc"] | None = None
    seed_number: int | None = Field(default=None, ge=1)
    checked_in: bool | None = None
    notes: str | None = None


class EventRegistrationResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    event_id: str
    team_id: str
    competition_level_id: str | None
    category: str
    seed_number: int | None
    checked_in_at: datetime | None
    notes: str | None
    registered_at: datetime


class EventPhaseCreate(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    phase_type: PhaseType
    sort_order: int = Field(ge=0)
    status: PhaseStatus = "draft"
    rounds: int = Field(default=3, ge=1, le=100)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    settings: dict = Field(default_factory=dict)


class EventPhaseUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    phase_type: PhaseType | None = None
    sort_order: int | None = Field(default=None, ge=0)
    status: PhaseStatus | None = None
    rounds: int | None = Field(default=None, ge=1, le=100)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    settings: dict | None = None


class EventPhaseResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    event_id: str
    name: str
    phase_type: str
    sort_order: int
    status: str
    rounds: int
    starts_at: datetime | None
    ends_at: datetime | None
    settings: dict


class ScheduleGenerateRequest(BaseModel):
    phase_id: str
    starts_at: datetime
    slot_minutes: int = Field(default=10, ge=3, le=240)
    table_count: int | None = Field(default=None, ge=1, le=100)
    team_ids: list[str] | None = None
    replace_existing: bool = False


class MatchParticipantResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    team_id: str | None
    position: int
    side: str | None
    result: str | None
    score: float | None


class ScheduledMatchResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    event_id: str
    phase_id: str
    code: str
    round_number: int
    sequence_number: int
    table_number: int | None
    scheduled_at: datetime | None
    duration_minutes: int
    status: str
    bracket: str | None
    next_winner_match_id: str | None
    next_loser_match_id: str | None
    version: int
    notes: str | None
    participants: list[MatchParticipantResponse]


class ScheduledMatchUpdate(BaseModel):
    scheduled_at: datetime | None = None
    table_number: int | None = Field(default=None, ge=1, le=100)
    duration_minutes: int | None = Field(default=None, ge=3, le=240)
    status: Literal["scheduled", "called", "running", "completed", "cancelled"] | None = None
    notes: str | None = None
    expected_version: int = Field(ge=1)


class EventScoreCreate(BaseModel):
    scheduled_match_id: str | None = None
    team_id: str
    competition_level_id: str | None = None
    round_number: int = Field(default=1, ge=1)
    table_number: int | None = Field(default=None, ge=1)
    raw_scores: dict = Field(default_factory=dict)
    notes: str | None = None
    idempotency_key: str = Field(min_length=8, max_length=100)


class ScoringFieldDefinition(BaseModel):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]*$", max_length=100)
    label: str = Field(min_length=1, max_length=255)
    type: Literal["count", "number", "boolean"] = "count"
    multiplier: float = 1.0
    min_value: float | None = None
    max_value: float | None = None
    required: bool = False
    section: str | None = Field(default=None, max_length=120)

    @model_validator(mode="after")
    def validate_range(self) -> "ScoringFieldDefinition":
        if (
            self.min_value is not None
            and self.max_value is not None
            and self.max_value < self.min_value
        ):
            raise ValueError("max_value must be greater than or equal to min_value")
        return self


class ScoringSchemaVersionCreate(BaseModel):
    competition_level_id: str | None = None
    fields: list[ScoringFieldDefinition] = Field(min_length=1)
    activate: bool = True


class ScoringSchemaResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    season_id: str
    event_id: str | None
    competition_level_id: str | None
    fields: list[dict]
    version: int
    is_active: bool
    created_at: datetime


class PublicResultResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    event_id: str
    scheduled_match_id: str | None
    team_id: str
    round_number: int
    table_number: int | None
    raw_scores: dict
    total_score: float
    is_disqualified: bool
    yellow_card: bool
    red_card: bool
    created_at: datetime


class PublicAnnouncementResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    title: str
    body: str
    published_at: datetime | None
    expires_at: datetime | None
