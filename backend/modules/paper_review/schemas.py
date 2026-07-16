from datetime import datetime
from pydantic import BaseModel, Field


class PaperCreate(BaseModel):
    season_id: str
    team_id: str
    title: str
    abstract: str | None = None
    competition_level_id: str | None = None
    notes: str | None = None


class PaperUpdate(BaseModel):
    title: str | None = None
    abstract: str | None = None
    notes: str | None = None


class ReviewerAssignmentCreate(BaseModel):
    reviewer_id: str


class ReviewCreateUpdate(BaseModel):
    # Each criterion is scored 0-10; finalize_paper divides the mean by 10 to
    # get final_score, so out-of-range values would push it outside 0-1 and
    # skew the overall competition ranking.
    score_content: float | None = Field(default=None, ge=0, le=10)
    score_methodology: float | None = Field(default=None, ge=0, le=10)
    score_presentation: float | None = Field(default=None, ge=0, le=10)
    score_originality: float | None = Field(default=None, ge=0, le=10)
    comments: str | None = None
    private_notes: str | None = None
    recommendation: str | None = None


class ReviewResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    paper_id: str
    reviewer_id: str
    revision_number: int
    score_content: float | None
    score_methodology: float | None
    score_presentation: float | None
    score_originality: float | None
    total_score: float | None
    comments: str | None
    recommendation: str | None
    is_submitted: bool
    submitted_at: datetime | None
    created_at: datetime


class ReviewerAssignmentResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    paper_id: str
    reviewer_id: str
    assigned_at: datetime


class PaperResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    season_id: str
    team_id: str
    title: str
    abstract: str | None
    competition_level_id: str | None
    status: str
    file_url: str | None
    file_name: str | None
    file_size_bytes: int | None
    submitted_at: datetime | None
    revision_number: int
    final_score: float | None
    paper_rank: int | None
    notes: str | None
    created_at: datetime
    updated_at: datetime
    reviews: list[ReviewResponse]
    assignments: list[ReviewerAssignmentResponse]


class PaperListItem(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    season_id: str
    team_id: str
    title: str
    status: str
    revision_number: int
    final_score: float | None
    paper_rank: int | None
    submitted_at: datetime | None
    created_at: datetime
