from datetime import datetime
from pydantic import BaseModel, field_validator


# ── Double Elimination ────────────────────────────────────────────────────────

class DEResultUpsert(BaseModel):
    team_id: str
    bracket: str  # "A" | "B"
    de_rank: int | None = None
    bracket_score: float | None = None
    de_score: float | None = None
    notes: str | None = None

    @field_validator("bracket")
    @classmethod
    def bracket_must_be_ab(cls, v: str) -> str:
        if v.upper() not in ("A", "B"):
            raise ValueError("bracket must be 'A' or 'B'")
        return v.upper()


class DEResultResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    season_id: str
    team_id: str
    bracket: str
    de_rank: int | None
    bracket_score: float | None
    de_score: float | None
    notes: str | None
    updated_at: datetime


# ── Aerial ────────────────────────────────────────────────────────────────────

class AerialResultUpsert(BaseModel):
    team_id: str
    run1: float | None = None
    run2: float | None = None
    run3: float | None = None
    run4: float | None = None
    notes: str | None = None


class AerialResultResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    season_id: str
    team_id: str
    run1: float | None
    run2: float | None
    run3: float | None
    run4: float | None
    score: float | None
    rank: int | None
    notes: str | None
    updated_at: datetime


# ── Documentation ─────────────────────────────────────────────────────────────

class DocScoreUpsert(BaseModel):
    team_id: str
    part1: float | None = None
    part2: float | None = None
    part3: float | None = None
    onsite: float | None = None
    notes: str | None = None


class DocScoreResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    season_id: str
    team_id: str
    part1: float | None
    part2: float | None
    part3: float | None
    onsite: float | None
    doc_score: float | None
    doc_rank: int | None
    notes: str | None
    updated_at: datetime


# ── Overall Ranking ───────────────────────────────────────────────────────────

class OverallRankingEntry(BaseModel):
    rank: int
    team_id: str
    team_name: str | None
    category: str
    overall_score: float
    seeding_score: float | None
    de_score: float | None
    paper_score: float | None
    doc_score: float | None
    aerial_score: float | None


class TeamRankingEntry(BaseModel):
    """Extended seeding ranking entry with team name and category."""
    rank: int
    team_id: str
    team_name: str | None
    category: str
    seed_score: float
    best_score: float
    average_score: float
    rounds_played: int
