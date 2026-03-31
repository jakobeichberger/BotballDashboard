from datetime import datetime
from pydantic import BaseModel


class MatchCreate(BaseModel):
    season_id: str
    phase_id: str | None = None
    team_id: str
    competition_level_id: str | None = None
    round_number: int = 1
    table_number: int | None = None
    raw_scores: dict = {}
    notes: str | None = None


class MatchUpdate(BaseModel):
    raw_scores: dict | None = None
    total_score: float | None = None
    is_disqualified: bool | None = None
    yellow_card: bool | None = None
    red_card: bool | None = None
    notes: str | None = None


class MatchResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    season_id: str
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
    entered_by: str | None
    confirmed_by: str | None
    confirmed_at: datetime | None
    created_at: datetime


class RankingResponse(BaseModel):
    model_config = {"from_attributes": True}

    rank: int
    team_id: str
    seed_score: float
    best_score: float
    average_score: float
    rounds_played: int
    updated_at: datetime


class ScoreBulkEntry(BaseModel):
    """Used for rapid multi-match entry (e.g., score table entry)."""
    entries: list[MatchCreate]
