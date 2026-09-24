from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

PaperStatus = Literal[
    "draft",
    "submitted",
    "under_review",
    "revision_requested",
    "resubmitted",
    "accepted",
    "rejected",
    "disqualified_ai",
]


class PaperCreate(BaseModel):
    season_id: str
    event_id: str | None = None
    team_id: str
    title: str
    abstract: str | None = None
    competition_level_id: str | None = None
    notes: str | None = None


class PaperUpdate(BaseModel):
    """What the submitting team may change about its own paper.

    final_score and paper_rank are deliberately absent: they are the review
    outcome, they feed the overall ranking, and papers:write is granted to
    mentors — so leaving them here let any mentor score every team's paper.
    They live on PaperScoreUpdate behind papers:admin instead.
    """

    title: str | None = None
    abstract: str | None = None
    notes: str | None = None


class PaperScoreUpdate(BaseModel):
    """The review outcome, settable only by papers:admin.

    format_deduction is in points on the 0-100 paper scale (a format violation
    can cost up to 100 %); finalize_paper subtracts it from the reviewers'
    average.
    """

    final_score: float | None = Field(default=None, ge=0, le=1)
    paper_rank: int | None = Field(default=None, ge=1)
    format_deduction: float | None = Field(default=None, ge=0, le=100)
    format_deduction_reason: str | None = None


class ReviewerAssignmentCreate(BaseModel):
    reviewer_id: str
    due_at: datetime | None = None


class ReviewCreateUpdate(BaseModel):
    # Each criterion is scored 0-10; finalize_paper divides the mean by 10 to
    # get final_score, so out-of-range values would push it outside 0-1 and
    # skew the overall competition ranking.
    score_content: float | None = Field(default=None, ge=0, le=10)
    score_implementation: float | None = Field(default=None, ge=0, le=10)
    score_results: float | None = Field(default=None, ge=0, le=10)
    score_language: float | None = Field(default=None, ge=0, le=10)
    score_format: float | None = Field(default=None, ge=0, le=10)
    comment_content: str | None = None
    comment_implementation: str | None = None
    comment_results: str | None = None
    comment_language: str | None = None
    comment_format: str | None = None
    comments: str | None = None
    revision_notes: str | None = None
    private_notes: str | None = None
    recommendation: Literal["accept", "reject", "revision_minor", "revision_major"] | None = None


class ReviewFeedback(BaseModel):
    """A submitted review as the paper's team sees it: scores and comments,
    but neither the reviewer's identity nor their private notes."""

    model_config = {"from_attributes": True}

    id: str
    revision_number: int
    version_number: int | None
    score_content: float | None
    score_implementation: float | None
    score_results: float | None
    score_language: float | None
    score_format: float | None
    comment_content: str | None
    comment_implementation: str | None
    comment_results: str | None
    comment_language: str | None
    comment_format: str | None
    total_score: float | None
    comments: str | None
    revision_notes: str | None
    recommendation: str | None
    submitted_at: datetime | None


class ReviewResponse(ReviewFeedback):
    """Full review: for organizers and the reviewer who wrote it."""

    paper_id: str
    reviewer_id: str
    private_notes: str | None
    is_submitted: bool
    created_at: datetime


class ReviewerAssignmentResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    paper_id: str
    reviewer_id: str
    assigned_at: datetime
    due_at: datetime | None
    status: str
    version_number: int | None
    reminder_sent_at: datetime | None
    completed_at: datetime | None


class PaperVersionResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    version_number: int
    revision_number: int
    file_name: str
    file_size_bytes: int
    uploaded_by: str | None
    uploaded_at: datetime
    submitted_at: datetime | None


class PaperDeadlineInfo(BaseModel):
    """The season's paper deadline as a concrete instant.

    deadline_date is the calendar day from the season; cutoff_at is the end of
    that day in the event's timezone (UTC). locked is what applies to the
    caller: False for papers:admin even after the cut-off (override).
    """

    deadline_date: date | None
    timezone: str
    cutoff_at: datetime | None
    passed: bool
    locked: bool
    can_override: bool


class PaperResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    season_id: str
    event_id: str | None
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
    current_version: int | None
    final_score: float | None
    paper_rank: int | None
    format_deduction: float
    format_deduction_reason: str | None
    finalized_at: datetime | None
    notes: str | None
    created_at: datetime
    updated_at: datetime
    reviews: list[ReviewResponse]
    assignments: list[ReviewerAssignmentResponse]
    versions: list[PaperVersionResponse] = []
    # Reviewer feedback released to the team (decided rounds only).
    feedback: list[ReviewFeedback] = []
    deadline: PaperDeadlineInfo | None = None


class PaperListItem(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    season_id: str
    event_id: str | None
    team_id: str
    title: str
    status: str
    revision_number: int
    current_version: int | None = None
    final_score: float | None
    paper_rank: int | None
    submitted_at: datetime | None
    created_at: datetime


class PaperStatusHistoryResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    paper_id: str
    from_status: str | None
    to_status: str
    reason: str | None
    changed_by: str | None
    changed_at: datetime


class ReviewerWorkloadResponse(BaseModel):
    reviewer_id: str
    assigned: int
    open: int
    overdue: int
    completed: int


class PaperStatsResponse(BaseModel):
    """Season/event overview for organizers."""

    total: int
    by_status: dict[str, int]
    decided: int
    accepted: int
    rejected: int
    disqualified: int
    # accepted / (accepted + rejected + disqualified); None while nothing is decided.
    acceptance_rate: float | None
    average_final_score: float | None
    average_review_score: float | None
    criterion_averages: dict[str, float | None]
    reviews_submitted: int
    reviews_open: int
    average_revision_rounds: float | None
