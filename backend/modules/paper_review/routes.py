import asyncio

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import (
    assert_team_access,
    has_elevated_access,
    own_team_ids,
    require_permission,
)
from core.database import get_db
from core.rate_limit import rate_limit
from modules.paper_review import assignment, deadlines, diff, service
from modules.paper_review.schemas import (
    AutoAssignRequest,
    AutoAssignResponse,
    PaperCreate,
    PaperDeadlineCreate,
    PaperDeadlineInfo,
    PaperDeadlineResponse,
    PaperDeadlineUpdate,
    PaperListItem,
    PaperResponse,
    PaperScoreUpdate,
    PaperStatsResponse,
    PaperStatus,
    PaperStatusHistoryResponse,
    PaperUpdate,
    PaperVersionDiff,
    PaperVersionResponse,
    ReviewCreateUpdate,
    ReviewerAssignmentCreate,
    ReviewerAssignmentResponse,
    ReviewerWorkloadResponse,
    ReviewFeedback,
    ReviewResponse,
)

router = APIRouter(prefix="/papers", tags=["papers"])

# Organizers and reviewers work across all teams; anyone else holding
# papers:read (a mentor) only sees their own team's papers.
_ALL_PAPERS = ("papers:admin", "papers:review")


async def _assert_paper_read(db: AsyncSession, user, paper) -> None:
    await assert_team_access(db, user, paper.team_id, _ALL_PAPERS)


async def _is_paper_admin(db: AsyncSession, user) -> bool:
    return await has_elevated_access(db, user, "papers:admin")


async def _paper_response(db: AsyncSession, user, paper) -> PaperResponse:
    """Serialize a paper for `user`.

    Organizers see every review. A reviewer only gets their own review back
    (for editing). The paper's own team gets `feedback`: the submitted reviews
    of decided rounds, without reviewer identity or drafts.
    """
    is_admin = await _is_paper_admin(db, user)
    resp = PaperResponse.model_validate(paper)
    if not is_admin:
        resp.reviews = [r for r in resp.reviews if r.reviewer_id == user.id]
    if is_admin or paper.team_id in await own_team_ids(db, user):
        resp.feedback = [ReviewFeedback.model_validate(r) for r in service.team_feedback(paper)]
    resp.deadline = PaperDeadlineInfo.model_validate(
        await service.deadline_info(db, paper.season_id, paper.event_id, is_admin)
    )
    return resp


@router.get("", response_model=list[PaperListItem])
async def list_papers(
    season_id: str | None = Query(None),
    team_id: str | None = Query(None),
    status: str | None = Query(None),
    event_id: str | None = Query(None),
    current_user=Depends(require_permission("papers:read")),
    db: AsyncSession = Depends(get_db),
):
    team_ids = None
    if not await has_elevated_access(db, current_user, _ALL_PAPERS):
        team_ids = await own_team_ids(db, current_user)
    return await service.list_papers(db, season_id, team_id, status, event_id, team_ids)


@router.get("/deadline", response_model=PaperDeadlineInfo)
async def get_paper_deadline(
    season_id: str = Query(...),
    event_id: str | None = Query(None),
    current_user=Depends(require_permission("papers:read")),
    db: AsyncSession = Depends(get_db),
):
    """The season's paper deadline, resolved to the event's timezone."""
    return await service.deadline_info(
        db, season_id, event_id, await _is_paper_admin(db, current_user)
    )


@router.get("/deadlines", response_model=list[PaperDeadlineResponse])
async def list_paper_deadlines(
    season_id: str = Query(...),
    _=Depends(require_permission("papers:read")),
    db: AsyncSession = Depends(get_db),
):
    """Official and internal paper deadlines of a season."""
    return await deadlines.list_deadlines(db, season_id)


@router.post("/deadlines", response_model=PaperDeadlineResponse, status_code=201)
async def create_paper_deadline(
    body: PaperDeadlineCreate,
    _=Depends(require_permission("papers:admin")),
    db: AsyncSession = Depends(get_db),
):
    return await deadlines.create_deadline(db, body.model_dump())


@router.patch("/deadlines/{deadline_id}", response_model=PaperDeadlineResponse)
async def update_paper_deadline(
    deadline_id: str,
    body: PaperDeadlineUpdate,
    _=Depends(require_permission("papers:admin")),
    db: AsyncSession = Depends(get_db),
):
    return await deadlines.update_deadline(db, deadline_id, body.model_dump(exclude_unset=True))


@router.delete("/deadlines/{deadline_id}", status_code=204)
async def delete_paper_deadline(
    deadline_id: str,
    _=Depends(require_permission("papers:admin")),
    db: AsyncSession = Depends(get_db),
):
    await deadlines.delete_deadline(db, deadline_id)


@router.post("/auto-assign", response_model=AutoAssignResponse)
async def auto_assign_reviewers(
    body: AutoAssignRequest,
    current_user=Depends(require_permission("papers:admin")),
    db: AsyncSession = Depends(get_db),
):
    """Give every open paper up to N reviewers, balancing the reviewers'
    workload and skipping conflicts of interest (own team, same school)."""
    return await assignment.auto_assign(
        db,
        season_id=body.season_id,
        event_id=body.event_id,
        reviewers_per_paper=body.reviewers_per_paper,
        assigned_by=current_user.id,
        reviewer_ids=body.reviewer_ids,
        due_at=body.due_at,
        dry_run=body.dry_run,
    )


@router.get("/stats", response_model=PaperStatsResponse)
async def get_paper_stats(
    season_id: str | None = Query(None),
    event_id: str | None = Query(None),
    _=Depends(require_permission("papers:admin")),
    db: AsyncSession = Depends(get_db),
):
    """Averages, acceptance rate and review progress for organizers."""
    return await service.paper_stats(db, season_id, event_id)


@router.post("", response_model=PaperResponse, status_code=201)
async def create_paper(
    body: PaperCreate,
    current_user=Depends(require_permission("papers:write")),
    db: AsyncSession = Depends(get_db),
):
    # Organizers (papers:admin) may file for any team and past the deadline;
    # mentors only for their own team and in time.
    await assert_team_access(db, current_user, body.team_id, "papers:admin")
    paper = await service.create_paper(
        db, body.model_dump(), override_deadline=await _is_paper_admin(db, current_user)
    )
    return await _paper_response(db, current_user, paper)


@router.get("/{paper_id}", response_model=PaperResponse)
async def get_paper(
    paper_id: str,
    current_user=Depends(require_permission("papers:read")),
    db: AsyncSession = Depends(get_db),
):
    paper = await service.get_paper(db, paper_id)
    await _assert_paper_read(db, current_user, paper)
    return await _paper_response(db, current_user, paper)


@router.get("/{paper_id}/feedback", response_model=list[ReviewFeedback])
async def get_paper_feedback(
    paper_id: str,
    current_user=Depends(require_permission("papers:read")),
    db: AsyncSession = Depends(get_db),
):
    """Reviewer feedback released to the paper's team (decided rounds only)."""
    paper = await service.get_paper(db, paper_id)
    await assert_team_access(db, current_user, paper.team_id, "papers:admin")
    return service.team_feedback(paper)


@router.patch("/{paper_id}", response_model=PaperResponse)
async def update_paper(
    paper_id: str,
    body: PaperUpdate,
    current_user=Depends(require_permission("papers:write")),
    db: AsyncSession = Depends(get_db),
):
    paper = await service.get_paper(db, paper_id)
    await assert_team_access(db, current_user, paper.team_id, "papers:admin")
    paper = await service.update_paper(db, paper_id, **body.model_dump(exclude_none=True))
    return await _paper_response(db, current_user, paper)


@router.post(
    "/{paper_id}/upload",
    response_model=PaperResponse,
    dependencies=[Depends(rate_limit("paper-upload", 20, 60))],
)
async def upload_paper_file(
    paper_id: str,
    file: UploadFile = File(...),
    current_user=Depends(require_permission("papers:write")),
    db: AsyncSession = Depends(get_db),
):
    """Upload the PDF as a new version (drafts and requested revisions only)."""
    # Validate the record and the caller's access before writing anything to disk.
    paper = await service.get_paper(db, paper_id)
    await assert_team_access(db, current_user, paper.team_id, "papers:admin")
    paper = await service.add_version(
        db,
        paper_id,
        file,
        current_user.id,
        override_deadline=await _is_paper_admin(db, current_user),
    )
    return await _paper_response(db, current_user, paper)


@router.get("/{paper_id}/versions", response_model=list[PaperVersionResponse])
async def list_paper_versions(
    paper_id: str,
    current_user=Depends(require_permission("papers:read")),
    db: AsyncSession = Depends(get_db),
):
    paper = await service.get_paper(db, paper_id)
    await _assert_paper_read(db, current_user, paper)
    return paper.versions


@router.get("/{paper_id}/versions/diff", response_model=PaperVersionDiff)
async def diff_paper_versions(
    paper_id: str,
    from_version: int | None = Query(None, ge=1),
    to_version: int | None = Query(None, ge=1),
    current_user=Depends(require_permission("papers:read")),
    db: AsyncSession = Depends(get_db),
):
    """Text diff between two PDF versions (default: previous vs. latest)."""
    paper = await service.get_paper(db, paper_id)
    await _assert_paper_read(db, current_user, paper)
    # PDF parsing is CPU-bound; keep it off the event loop.
    return await asyncio.to_thread(diff.version_diff, paper, from_version, to_version)


@router.get("/{paper_id}/download")
async def download_paper(
    paper_id: str,
    version: int | None = Query(None, ge=1),
    current_user=Depends(require_permission("papers:read")),
    db: AsyncSession = Depends(get_db),
):
    """Download one version of the PDF (default: the latest)."""
    paper = await service.get_paper(db, paper_id)
    await _assert_paper_read(db, current_user, paper)
    file_path, file_name = service.resolve_version_file(paper, version)
    return FileResponse(
        str(file_path),
        filename=file_name,
        media_type="application/pdf",
        content_disposition_type="attachment",
    )


@router.put("/{paper_id}/submit", response_model=PaperResponse)
async def submit_paper(
    paper_id: str,
    current_user=Depends(require_permission("papers:write")),
    db: AsyncSession = Depends(get_db),
):
    paper = await service.get_paper(db, paper_id)
    await assert_team_access(db, current_user, paper.team_id, "papers:admin")
    paper = await service.submit_paper(
        db,
        paper_id,
        current_user.id,
        override_deadline=await _is_paper_admin(db, current_user),
    )
    return await _paper_response(db, current_user, paper)


@router.put("/{paper_id}/status", response_model=PaperResponse)
async def set_paper_status(
    paper_id: str,
    status: PaperStatus = Query(...),
    reason: str | None = Query(None, max_length=2000),
    current_user=Depends(require_permission("papers:admin")),
    db: AsyncSession = Depends(get_db),
):
    """Set the status. disqualified_ai records AI misuse: score 0, no revision."""
    paper = await service.set_paper_status(db, paper_id, status, current_user.id, reason)
    return await _paper_response(db, current_user, paper)


@router.post("/{paper_id}/finalize", response_model=PaperResponse)
async def finalize_paper(
    paper_id: str,
    current_user=Depends(require_permission("papers:admin")),
    db: AsyncSession = Depends(get_db),
):
    """Aggregate submitted reviews (minus format deductions) into final_score,
    lock the round's reviews and recompute paper ranks."""
    paper = await service.finalize_paper(db, paper_id)
    return await _paper_response(db, current_user, paper)


# ── Reviewer assignments ──────────────────────────────────────────────────────


@router.post("/{paper_id}/assignments", response_model=ReviewerAssignmentResponse, status_code=201)
async def assign_reviewer(
    paper_id: str,
    body: ReviewerAssignmentCreate,
    current_user=Depends(require_permission("papers:admin")),
    db: AsyncSession = Depends(get_db),
):
    return await service.assign_reviewer(
        db, paper_id, body.reviewer_id, current_user.id, body.due_at
    )


@router.post(
    "/{paper_id}/assignments/{assignment_id}/remind",
    response_model=ReviewerAssignmentResponse,
)
async def remind_reviewer(
    paper_id: str,
    assignment_id: str,
    _=Depends(require_permission("papers:admin")),
    db: AsyncSession = Depends(get_db),
):
    return await service.mark_reminder_sent(db, paper_id, assignment_id)


@router.put("/{paper_id}/score", response_model=PaperResponse)
async def set_paper_score(
    paper_id: str,
    body: PaperScoreUpdate,
    current_user=Depends(require_permission("papers:admin")),
    db: AsyncSession = Depends(get_db),
):
    """Record the review outcome or a format deduction. Separate from
    PATCH /{paper_id} because final_score feeds the overall ranking and
    papers:write reaches mentors. Deductions take effect on finalize."""
    paper = await service.update_paper(db, paper_id, **body.model_dump(exclude_none=True))
    return await _paper_response(db, current_user, paper)


@router.get("/reviewers/workload", response_model=list[ReviewerWorkloadResponse])
async def get_reviewer_workload(
    event_id: str | None = Query(None),
    _=Depends(require_permission("papers:admin")),
    db: AsyncSession = Depends(get_db),
):
    return await service.reviewer_workload(db, event_id)


# ── Reviews ───────────────────────────────────────────────────────────────────


@router.put("/{paper_id}/reviews", response_model=ReviewResponse)
async def save_review(
    paper_id: str,
    body: ReviewCreateUpdate,
    submit: bool = Query(False),
    current_user=Depends(require_permission("papers:review")),
    db: AsyncSession = Depends(get_db),
):
    """Save (or with ?submit=true, submit) the caller's review of the current
    version. A submitted review is locked until an organizer reopens it."""
    return await service.save_review(
        db, paper_id, current_user.id, body.model_dump(exclude_none=True), submit=submit
    )


@router.post("/{paper_id}/reviews/{review_id}/reopen", response_model=ReviewResponse)
async def reopen_review(
    paper_id: str,
    review_id: str,
    _=Depends(require_permission("papers:admin")),
    db: AsyncSession = Depends(get_db),
):
    return await service.reopen_review(db, paper_id, review_id)


@router.get("/{paper_id}/reviews", response_model=list[ReviewResponse])
async def list_reviews(
    paper_id: str,
    _=Depends(require_permission("papers:admin")),
    db: AsyncSession = Depends(get_db),
):
    paper = await service.get_paper(db, paper_id)
    return paper.reviews


@router.get("/{paper_id}/history", response_model=list[PaperStatusHistoryResponse])
async def get_paper_history(
    paper_id: str,
    current_user=Depends(require_permission("papers:read")),
    db: AsyncSession = Depends(get_db),
):
    await _assert_paper_read(db, current_user, await service.get_paper(db, paper_id))
    return await service.list_status_history(db, paper_id)
