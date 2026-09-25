from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from modules.seasons.categories import CategoryKey

_KEY = r"^[a-z][a-z0-9_]*$"


# ── Season rules: tie-breakers, finals replay, checklist ─────────────────────


class TiebreakerCriterion(BaseModel):
    key: str = Field(pattern=_KEY, max_length=100)
    label: str = Field(min_length=1, max_length=255)
    direction: Literal["max", "min"] = "max"
    # sheet: summed from the listed raw score-sheet values; entry: typed in by the juror
    source: Literal["sheet", "entry"] = "entry"
    sheet_keys: list[str] = Field(default_factory=list, max_length=20)
    replay_only: bool = False

    @model_validator(mode="after")
    def validate_source(self) -> "TiebreakerCriterion":
        if self.source == "sheet" and not self.sheet_keys:
            raise ValueError(f"{self.key}: a sheet criterion needs at least one sheet key")
        if self.key == "replayed":
            raise ValueError("'replayed' is reserved")
        return self


class ChecklistItem(BaseModel):
    key: str = Field(pattern=_KEY, max_length=100)
    label: str = Field(min_length=1, max_length=255)
    required: bool = True
    # The rule text, e.g. the game review's wording, shown under the label.
    description: str | None = Field(default=None, max_length=2000)


class DocMaxPoints(BaseModel):
    """Rubric maximum of each documentation period (2026: 100 / 95 / 100 / 100)."""

    p1: float = Field(default=100.0, gt=0, le=1000)
    p2: float = Field(default=100.0, gt=0, le=1000)
    p3: float = Field(default=100.0, gt=0, le=1000)
    onsite: float = Field(default=100.0, gt=0, le=1000)


class RuleSetUpdate(BaseModel):
    tiebreakers: list[TiebreakerCriterion] = Field(default_factory=list, max_length=30)
    finals_replay: bool = False
    end_contact_bonus_percent: float = Field(default=25.0, ge=0, le=100)
    referee_checklist: list[ChecklistItem] = Field(default_factory=list, max_length=40)
    # Off: equal seed scores share a rank (game review, ECER 2026).
    seeding_tiebreakers: bool = False
    doc_max_points: DocMaxPoints = Field(default_factory=DocMaxPoints)

    @model_validator(mode="after")
    def unique_keys(self) -> "RuleSetUpdate":
        for name, keys in (
            ("tie-breaker", [item.key for item in self.tiebreakers]),
            ("checklist", [item.key for item in self.referee_checklist]),
        ):
            if len(keys) != len(set(keys)):
                raise ValueError(f"Duplicate {name} key")
        return self


class RuleSetResponse(RuleSetUpdate):
    season_id: str


class TimeoutCardCreate(BaseModel):
    team_id: str
    scheduled_match_id: str | None = None
    round_number: int | None = Field(default=None, ge=1)
    reason: Literal["before_hands_off", "inspection"] = "before_hands_off"
    note: str | None = Field(default=None, max_length=2000)


class TimeoutCardResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    event_id: str
    team_id: str
    team_name: str | None = None
    scheduled_match_id: str | None
    round_number: int | None
    reason: str
    note: str | None
    recorded_by: str | None
    used_at: datetime


class ChecklistPreset(BaseModel):
    id: str
    name: str
    items: list[ChecklistItem]


class TiebreakerPreset(BaseModel):
    id: str
    name: str
    finals_replay: bool
    tiebreakers: list[TiebreakerCriterion]


# ── Schema templates / clone ──────────────────────────────────────────────────


class SchemaTemplateResponse(BaseModel):
    id: str
    name: str
    year: int
    complete: bool
    source: str
    notes: str
    definition: dict


class SchemaListEntry(BaseModel):
    id: str
    season_id: str
    season_name: str | None
    event_id: str | None
    event_name: str | None
    competition_level_id: str | None
    competition_level_name: str | None
    version: int
    structured: bool
    field_count: int


class SchemaClone(BaseModel):
    source_schema_id: str
    competition_level_id: str | None = None
    activate: bool = True


# ── Head to head / DE placement ───────────────────────────────────────────────


class HeadToHeadSide(BaseModel):
    match_id: str
    team_id: str
    team_name: str | None
    sheet_score: float
    bonus_score: float
    total_score: float
    is_disqualified: bool
    round_lost: bool
    round_lost_reason: str | None
    end_contact: bool


class HeadToHeadOutcome(BaseModel):
    scheduled_match_id: str
    winner: str | None
    reason: str
    decided_by: str | None
    replay: bool
    sides: list[HeadToHeadSide]


class DEPlacementEntry(BaseModel):
    bracket: str
    team_id: str
    team_name: str | None
    de_rank: int | None
    placement: int
    decided_by: str | None


# ── Parts challenge ───────────────────────────────────────────────────────────


class PartsChallengeCreate(BaseModel):
    scheduled_match_id: str | None = None
    challenger_team_id: str
    challenged_team_id: str
    description: str = Field(min_length=3, max_length=2000)

    @model_validator(mode="after")
    def different_teams(self) -> "PartsChallengeCreate":
        if self.challenger_team_id == self.challenged_team_id:
            raise ValueError("A team cannot challenge itself")
        return self


class PartsChallengeRuling(BaseModel):
    upheld: bool
    ruling_note: str | None = Field(default=None, max_length=2000)


class PartsChallengeResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    event_id: str
    scheduled_match_id: str | None
    challenger_team_id: str
    challenged_team_id: str
    description: str
    upheld: bool | None
    ruling_note: str | None
    decided_by: str | None
    decided_at: datetime | None
    created_at: datetime


# ── Scouting ──────────────────────────────────────────────────────────────────


class ExternalTeamCreate(BaseModel):
    season_id: str
    name: str = Field(min_length=1, max_length=255)
    number: str | None = Field(default=None, max_length=50)
    country: str | None = Field(default=None, max_length=100)
    school: str | None = Field(default=None, max_length=255)
    source: Literal["observed", "official"] = "observed"
    notes: str | None = Field(default=None, max_length=5000)


class ExternalTeamUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    number: str | None = Field(default=None, max_length=50)
    country: str | None = Field(default=None, max_length=100)
    school: str | None = Field(default=None, max_length=255)
    source: Literal["observed", "official"] | None = None
    notes: str | None = Field(default=None, max_length=5000)


class ExternalTeamResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    season_id: str
    name: str
    number: str | None
    country: str | None
    school: str | None
    source: str
    notes: str | None
    # Lets the UI offer editing to the creator (organizers may edit any team).
    created_by: str | None = None
    created_at: datetime


class ScoutingNoteCreate(BaseModel):
    external_team_id: str
    # Required for mentors (their own team); organizers may leave it empty.
    owner_team_id: str | None = None
    body: str = Field(min_length=1, max_length=10000)
    threat_level: int | None = Field(default=None, ge=1, le=5)


class ScoutingNoteUpdate(BaseModel):
    body: str | None = Field(default=None, min_length=1, max_length=10000)
    threat_level: int | None = Field(default=None, ge=1, le=5)


class ScoutingNoteResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    event_id: str
    external_team_id: str
    owner_team_id: str | None
    author_id: str | None
    body: str
    threat_level: int | None
    created_at: datetime
    updated_at: datetime


class ObservationCreate(BaseModel):
    external_team_id: str
    owner_team_id: str | None = None
    phase: Literal["seeding", "double_seeding", "double_elimination", "alliance", "other"] = (
        "seeding"
    )
    round_number: int | None = Field(default=None, ge=1, le=100)
    score: float = Field(ge=-10000, le=100000)
    notes: str | None = Field(default=None, max_length=2000)


class ObservationResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    event_id: str
    external_team_id: str
    owner_team_id: str | None
    author_id: str | None
    phase: str
    round_number: int | None
    score: float
    notes: str | None
    created_at: datetime


class OpponentRankingEntry(BaseModel):
    rank: int
    kind: Literal["internal", "external"]
    team_id: str
    team_name: str
    team_number: str | None
    country: str | None
    seed_score: float
    best_score: float
    runs: int
    official_rank: int | None = None


# ── Qualification ─────────────────────────────────────────────────────────────


class QualifyRequest(BaseModel):
    season_id: str
    team_ids: list[str] = Field(min_length=1, max_length=100)
    note: str | None = Field(default=None, max_length=2000)
    source_event_id: str | None = None


class QualificationResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    season_id: str
    team_id: str
    team_name: str | None = None
    level_id: str
    from_level_id: str | None
    source_event_id: str | None
    note: str | None
    qualified_by: str | None
    created_at: datetime


class QualificationStatusEntry(BaseModel):
    team_id: str
    team_name: str
    qualified: bool
    qualification_id: str | None
    note: str | None


class RegisterQualifiedRequest(BaseModel):
    level_id: str
    category: CategoryKey = "botball"


class RegisteredTeam(BaseModel):
    """An event registration created by "register qualified teams"."""

    model_config = {"from_attributes": True}

    id: str
    event_id: str
    team_id: str
    team_name: str
    competition_level_id: str | None
    category: str
