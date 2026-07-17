from datetime import datetime

from pydantic import BaseModel, Field


class MatchCreate(BaseModel):
    event_id: str | None = None
    scheduled_match_id: str | None = None
    phase_id: str | None = None
    team_id: str
    competition_level_id: str | None = None
    round_number: int = 1
    table_number: int | None = None
    raw_scores: dict = Field(default_factory=dict)
    notes: str | None = None
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=100)


class MatchUpdate(BaseModel):
    raw_scores: dict | None = None
    total_score: float | None = None
    is_disqualified: bool | None = None
    yellow_card: bool | None = None
    red_card: bool | None = None
    notes: str | None = None
    expected_version: int | None = Field(default=None, ge=1)
    correction_reason: str | None = Field(default=None, max_length=1000)


class MatchResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    season_id: str
    event_id: str
    scheduled_match_id: str | None
    phase_id: str | None
    team_id: str
    competition_level_id: str | None
    round_number: int
    table_number: int | None
    raw_scores: dict
    total_score: float
    is_disqualified: bool
    yellow_card: bool
    red_card: bool
    notes: str | None
    schema_snapshot: dict | None
    version: int
    entered_by: str | None
    confirmed_by: str | None
    confirmed_at: datetime | None
    created_at: datetime


class RankingResponse(BaseModel):
    model_config = {"from_attributes": True}

    rank: int
    event_id: str
    team_id: str
    seed_score: float
    best_score: float
    average_score: float
    rounds_played: int
    updated_at: datetime


class ScoreBulkEntry(BaseModel):
    """Used for rapid multi-match entry (e.g., score table entry)."""

    entries: list[MatchCreate]


class ScoreRevisionResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    match_id: str
    event_id: str
    revision: int
    previous_value: dict | None
    new_value: dict
    reason: str | None
    changed_by: str | None
    created_at: datetime
