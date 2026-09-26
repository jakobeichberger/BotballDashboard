from datetime import UTC, datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, Field, field_validator, model_validator

from modules.events.module_access import MODULE_KEYS
from modules.scoring.sheet_schemas import SheetDefinition
from modules.seasons.categories import CategoryKey

EventStatus = Literal["draft", "published", "live", "completed", "archived"]
PhaseType = Literal["seeding", "double_seeding", "double_elimination", "alliance", "final"]
PhaseStatus = Literal["draft", "scheduled", "live", "completed"]


def _assume_utc(value: datetime) -> datetime:
    # A time without offset is read as UTC: PostgreSQL returns timestamptz
    # values, and comparing them with a naive datetime raises a TypeError.
    return value if value.tzinfo else value.replace(tzinfo=UTC)


UtcDatetime = Annotated[datetime, AfterValidator(_assume_utc)]


def _validate_module_names(value: list[str]) -> list[str]:
    invalid = set(value) - set(MODULE_KEYS)
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
    starts_at: UtcDatetime | None = None
    ends_at: UtcDatetime | None = None
    status: EventStatus = "draft"
    # None: derive from the season's module flags (module_access.modules_for_season).
    active_modules: list[str] | None = None
    public_scoreboard: bool = False
    public_schedule: bool = False
    public_results: bool = False
    public_announcements: bool = False
    table_count: int = Field(default=1, ge=1, le=100)
    notes: str | None = None

    @field_validator("active_modules")
    @classmethod
    def validate_modules(cls, value: list[str] | None) -> list[str] | None:
        return None if value is None else _validate_module_names(value)

    @model_validator(mode="after")
    def validate_dates(self) -> EventCreate:
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
    starts_at: UtcDatetime | None = None
    ends_at: UtcDatetime | None = None
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


class EventModulesResponse(BaseModel):
    """Module switches of one event, resolved against its season."""

    event_id: str
    available_modules: list[str]
    active_modules: list[str]
    effective_modules: list[str]
    # Season-level switches: use_seeding, use_double_elimination,
    # use_documentation_scoring, use_aerial, use_paper_scoring.
    season_flags: dict[str, bool]


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
    category: CategoryKey = "botball"
    seed_number: int | None = Field(default=None, ge=1)
    notes: str | None = None


class EventRegistrationUpdate(BaseModel):
    competition_level_id: str | None = None
    category: CategoryKey | None = None
    seed_number: int | None = Field(default=None, ge=1)
    checked_in: bool | None = None
    notes: str | None = None


class EventRegistrationResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    event_id: str
    team_id: str
    team_name: str
    team_number: str | None
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
    starts_at: UtcDatetime | None = None
    ends_at: UtcDatetime | None = None
    settings: dict = Field(default_factory=dict)


class EventPhaseUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    phase_type: PhaseType | None = None
    sort_order: int | None = Field(default=None, ge=0)
    status: PhaseStatus | None = None
    rounds: int | None = Field(default=None, ge=1, le=100)
    starts_at: UtcDatetime | None = None
    ends_at: UtcDatetime | None = None
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
    starts_at: UtcDatetime
    slot_minutes: int = Field(default=10, ge=3, le=240)
    table_count: int | None = Field(default=None, ge=1, le=100)
    team_ids: list[str] | None = None
    # Restrict the phase to the teams of one category (default: phase settings).
    category: CategoryKey | None = None
    replace_existing: bool = False


class MatchParticipantResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    team_id: str | None
    team_name: str | None
    team_number: str | None
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
    next_winner_slot: int | None = None
    next_loser_slot: int | None = None
    round_kind: str | None = None
    version: int
    notes: str | None
    participants: list[MatchParticipantResponse]


class MatchResultRequest(BaseModel):
    """Result of a scheduled match.

    Elimination phases need ``winner_team_id``; seeding-like and alliance
    phases record per-team ``scores`` (team id → score).
    """

    winner_team_id: str | None = None
    scores: dict[str, float] = Field(default_factory=dict)
    expected_version: int | None = Field(default=None, ge=1)


class SeedAssignmentRequest(BaseModel):
    category: CategoryKey | None = None
    phase_id: str | None = None


class BracketPlacement(BaseModel):
    team_id: str
    team_name: str
    team_number: str | None
    # Bracket placement, shared by teams knocked out in the same round.
    rank: int
    # The same order with ties broken by the season's tie-breakers / seeding rank.
    placement: int | None = None
    decided_by: str | None = None


class BracketPhaseResponse(BaseModel):
    phase_id: str
    phase_name: str
    phase_type: str
    status: str
    bracket_label: str
    matches: list[ScheduledMatchResponse]
    placements: list[BracketPlacement]


class AllianceRun(BaseModel):
    match_id: str
    round_number: int
    score: float


class AllianceStanding(BaseModel):
    rank: int
    team_ids: list[str]
    team_names: list[str]
    runs: list[AllianceRun]
    best_score: float
    total_score: float


class BracketWeightsUpdate(BaseModel):
    weights: dict[str, float]

    @field_validator("weights")
    @classmethod
    def validate_weights(cls, value: dict[str, float]) -> dict[str, float]:
        for bracket, weight in value.items():
            if not 1 <= len(bracket) <= 20:
                raise ValueError("Bracket labels have 1 to 20 characters")
            if weight < 0:
                raise ValueError("Bracket weights cannot be negative")
        return value


class ScheduledMatchUpdate(BaseModel):
    scheduled_at: UtcDatetime | None = None
    table_number: int | None = Field(default=None, ge=1, le=100)
    duration_minutes: int | None = Field(default=None, ge=3, le=240)
    status: Literal["scheduled", "called", "running", "completed", "cancelled"] | None = None
    notes: str | None = None
    expected_version: int = Field(ge=1)


class EventScoreCreate(BaseModel):
    scheduled_match_id: str | None = None
    team_id: str
    competition_level_id: str | None = None
    # None: the scheduled match's round, else round 1.
    round_number: int | None = Field(default=None, ge=1)
    table_number: int | None = Field(default=None, ge=1)
    raw_scores: dict = Field(default_factory=dict)
    # Special round conditions (game review "Tie Breakers & Special Scoring
    # Conditions"): lose the round → 0 points; end-of-game contact → the
    # opponent of a head-to-head match receives 25 % of this team's score.
    round_lost: bool = False
    round_lost_reason: Literal["never_left_start_box", "motors_running", "other"] | None = None
    end_contact: bool = False
    tiebreak_values: dict[str, float | bool | None] = Field(default_factory=dict)
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
    def validate_range(self) -> ScoringFieldDefinition:
        if (
            self.min_value is not None
            and self.max_value is not None
            and self.max_value < self.min_value
        ):
            raise ValueError("max_value must be greater than or equal to min_value")
        return self


class ScoringSchemaVersionCreate(BaseModel):
    """A flat field list, or a structured sheet (`definition`, see scoring.sheet)."""

    competition_level_id: str | None = None
    fields: list[ScoringFieldDefinition] = Field(default_factory=list)
    definition: SheetDefinition | None = None
    activate: bool = True

    @model_validator(mode="after")
    def validate_shape(self) -> ScoringSchemaVersionCreate:
        if self.definition is None and not self.fields:
            raise ValueError("Either fields or a structured definition is required")
        if self.definition is not None and self.fields:
            raise ValueError("Send either fields or a definition, not both")
        return self


class ScoringSchemaResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    season_id: str
    event_id: str | None
    competition_level_id: str | None
    fields: list[dict]
    definition: dict | None = None
    version: int
    is_active: bool
    created_at: datetime


class PublicResultResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    event_id: str
    scheduled_match_id: str | None
    team_id: str
    team_name: str
    team_number: str | None
    round_number: int
    table_number: int | None
    raw_scores: dict
    total_score: float
    is_disqualified: bool
    yellow_card: bool
    red_card: bool
    created_at: datetime


class PublicRankingResponse(BaseModel):
    rank: int
    team_id: str
    team_name: str
    team_number: str | None
    seed_score: float
    best_score: float
    average_score: float
    rounds_played: int
    updated_at: datetime


class PublicAnnouncementResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    title: str
    body: str
    published_at: datetime | None
    expires_at: datetime | None
