from datetime import datetime

from pydantic import BaseModel, Field, field_validator, model_validator

# ── Double Elimination ────────────────────────────────────────────────────────


class DEResultUpsert(BaseModel):
    # team_id is taken from the URL path by the route; optional in the body.
    team_id: str | None = None
    bracket: str  # "A" | "B"
    de_rank: int | None = Field(default=None, ge=1)
    bracket_score: float | None = Field(default=None, ge=0, le=1)
    de_score: float | None = Field(default=None, ge=0, le=1)
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
    event_id: str
    team_id: str
    bracket: str
    de_rank: int | None
    bracket_score: float | None
    de_score: float | None
    notes: str | None
    updated_at: datetime


# ── Aerial ────────────────────────────────────────────────────────────────────


MAX_AERIAL_RUNS = 20


class AerialResultUpsert(BaseModel):
    team_id: str | None = None
    # The scoring runs in order; null for a run not flown (yet).
    runs: list[float | None] = Field(default_factory=list, max_length=MAX_AERIAL_RUNS)
    # Former fixed columns, still accepted from older clients.
    run1: float | None = Field(default=None, ge=0, exclude=True)
    run2: float | None = Field(default=None, ge=0, exclude=True)
    run3: float | None = Field(default=None, ge=0, exclude=True)
    run4: float | None = Field(default=None, ge=0, exclude=True)
    notes: str | None = None

    @model_validator(mode="after")
    def normalise_runs(self) -> AerialResultUpsert:
        legacy = [self.run1, self.run2, self.run3, self.run4]
        if not self.runs and any(v is not None for v in legacy):
            self.runs = legacy
        if any(v is not None and v < 0 for v in self.runs):
            raise ValueError("Aerial runs must not be negative")
        while self.runs and self.runs[-1] is None:
            self.runs.pop()
        return self


class AerialResultResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    season_id: str
    event_id: str
    team_id: str
    runs: list[float | None]
    score: float | None
    rank: int | None
    notes: str | None
    updated_at: datetime


# ── Documentation ─────────────────────────────────────────────────────────────


class DocScoreUpsert(BaseModel):
    """Rubric points per period; the upper bound is the season's rubric maximum
    (ScoringRuleSet.doc_max_points, 2026: P1 /100, P2 /95, P3 /100, Onsite /100)."""

    team_id: str | None = None
    part1: float | None = Field(default=None, ge=0, le=1000)
    part2: float | None = Field(default=None, ge=0, le=1000)
    part3: float | None = Field(default=None, ge=0, le=1000)
    onsite: float | None = Field(default=None, ge=0, le=1000)
    notes: str | None = None


class DocScoreResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    season_id: str
    event_id: str
    team_id: str
    part1: float | None
    part2: float | None
    part3: float | None
    onsite: float | None
    doc_score: float | None
    doc_rank: int | None
    notes: str | None
    updated_at: datetime


# ── Junior Botball Challenge ──────────────────────────────────────────────────


class JBCChallenge(BaseModel):
    key: str = Field(min_length=1, max_length=50)
    label: str | None = Field(default=None, max_length=255)
    points: float = Field(ge=0, le=1000)


class JBCResultUpsert(BaseModel):
    team_id: str | None = None
    # Either the points directly or the solved challenges (points = their sum).
    points: float | None = Field(default=None, ge=0, le=10000)
    challenges: list[JBCChallenge] = Field(default_factory=list, max_length=100)
    notes: str | None = None


class JBCResultResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    season_id: str
    event_id: str
    team_id: str
    points: float | None
    challenges: list[dict]
    rank: int | None
    notes: str | None
    updated_at: datetime


# ── Overall Ranking ───────────────────────────────────────────────────────────


class OverallRankingEntry(BaseModel):
    # None when the team is disqualified (red card) and takes no place.
    rank: int | None
    disqualified: bool = False
    team_id: str
    team_name: str | None
    category: str
    overall_score: float
    seeding_score: float | None
    de_score: float | None
    paper_score: float | None
    doc_score: float | None
    aerial_score: float | None
    # Categories ranked per DE bracket (GCER courses/tiers): the bracket and
    # the team's place within it.
    course: str | None = None
    course_rank: int | None = None
    # Every value the season's formula set produced, including any custom keys
    # that have no dedicated field above.
    values: dict[str, float] = {}


class TeamRankingEntry(BaseModel):
    """Extended seeding ranking entry with team name and category."""

    rank: int | None
    disqualified: bool = False
    team_id: str
    team_name: str | None
    category: str
    seed_score: float
    best_score: float
    average_score: float
    rounds_played: int
    # Tie-breaker that placed the team against an equal seed score, if any.
    tiebreaker: str | None = None


class ResultRevisionResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    event_id: str
    team_id: str
    kind: str
    previous_value: dict | None
    new_value: dict | None
    changed_by: str | None
    created_at: datetime
