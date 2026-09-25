import uuid
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import aiofiles
from fastapi import HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.config import get_settings
from core.domain_events import emit_event
from core.exceptions import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from core.files import ensure_within, safe_filename
from modules.paper_review.models import (
    DECIDED_STATUSES,
    EDITABLE_STATUSES,
    REVIEW_CRITERIA,
    REVIEWABLE_STATUSES,
    Paper,
    PaperReview,
    PaperStatusHistory,
    PaperVersion,
    ReviewerAssignment,
)
from modules.scoring.service import resolve_event
from modules.seasons.lifecycle import ensure_writable

settings = get_settings()

DEFAULT_TIMEZONE = "Europe/Vienna"
# Final verdicts: the paper's review is over and it cannot be revised.
_CLOSED_STATUSES = frozenset({"accepted", "rejected", "disqualified_ai"})


async def ensure_paper_writable(db: AsyncSession, paper: Paper) -> None:
    """Papers of an archived season/event are read-only history."""
    await ensure_writable(db, season_id=paper.season_id, event_id=paper.event_id)


async def save_file(
    file: UploadFile, paper_id: str, version_number: int = 1
) -> tuple[str, str, int]:
    """Store an uploaded PDF as papers/<paper_id>/v<n>-<random>/<name>.

    Returns (absolute path, stored file name, size). Every upload gets its own
    directory (the random suffix keeps two racing uploads apart), so a new
    upload never overwrites a file a reviewer has judged.
    """
    if file.content_type and file.content_type not in (
        "application/pdf",
        "application/octet-stream",
    ):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    papers_dir = Path(settings.upload_dir) / "papers"
    upload_dir = ensure_within(
        papers_dir, papers_dir / paper_id / f"v{version_number}-{uuid.uuid4().hex[:8]}"
    )
    upload_dir.mkdir(parents=True, exist_ok=True)
    safe_name = safe_filename(file.filename, "paper.pdf")
    file_path = ensure_within(upload_dir, upload_dir / safe_name)
    temp_path = ensure_within(upload_dir, upload_dir / f".{safe_name}.upload")
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    size = 0
    signature = b""
    try:
        async with aiofiles.open(temp_path, "wb") as target:
            while chunk := await file.read(1024 * 1024):
                if not signature:
                    signature = chunk[:5]
                size += len(chunk)
                if size > max_bytes:
                    raise ValidationError("File too large")
                await target.write(chunk)
        if signature != b"%PDF-":
            raise ValidationError("Uploaded file is not a PDF")
        temp_path.replace(file_path)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise

    return str(file_path), safe_name, size


# ── Deadline ──────────────────────────────────────────────────────────────────


def deadline_cutoff(deadline: date, tz_name: str | None) -> datetime:
    """End of the deadline day in the event's timezone, as an aware UTC instant.

    The season stores the paper deadline as a calendar date; "15 March" means
    until midnight at the venue, not midnight UTC.
    """
    try:
        tz = ZoneInfo(tz_name or DEFAULT_TIMEZONE)
    except (ZoneInfoNotFoundError, ValueError):
        tz = ZoneInfo(DEFAULT_TIMEZONE)
    local_end = datetime.combine(deadline + timedelta(days=1), time.min, tzinfo=tz)
    return local_end.astimezone(UTC)


async def deadline_info(
    db: AsyncSession,
    season_id: str,
    event_id: str | None,
    can_override: bool,
    now: datetime | None = None,
) -> dict:
    from modules.events.models import Event
    from modules.paper_review import deadlines
    from modules.seasons.models import Season

    season = await db.get(Season, season_id)
    if not season:
        raise NotFoundError("Season not found")
    event = await db.get(Event, event_id) if event_id else None
    tz_name = event.timezone if event and event.timezone else DEFAULT_TIMEZONE
    now = now or datetime.now(UTC)
    # A blocking official_submission deadline takes precedence over the
    # season's plain date field.
    deadline = (
        await deadlines.hard_block_date(db, season_id, "official_submission")
        or season.paper_submission_deadline
    )
    cutoff = deadline_cutoff(deadline, tz_name) if deadline else None
    passed = bool(cutoff and now >= cutoff)
    final = await deadlines.hard_block_date(db, season_id, "official_final")
    final_cutoff = deadline_cutoff(final, tz_name) if final else None
    final_passed = bool(final_cutoff and now >= final_cutoff)
    all_deadlines = []
    for row in await deadlines.list_deadlines(db, season_id):
        row_cutoff = deadline_cutoff(row.due_date, tz_name)
        all_deadlines.append(
            {
                "id": row.id,
                "deadline_type": row.deadline_type,
                "due_date": row.due_date,
                "label": row.label,
                "is_hard_block": row.is_hard_block,
                "cutoff_at": row_cutoff,
                "passed": now >= row_cutoff,
            }
        )
    return {
        "deadline_date": deadline,
        "timezone": tz_name,
        "cutoff_at": cutoff,
        "passed": passed,
        "locked": passed and not can_override,
        "can_override": can_override,
        "final_deadline_date": final,
        "final_cutoff_at": final_cutoff,
        "final_locked": final_passed and not can_override,
        "deadlines": all_deadlines,
    }


async def _assert_before_deadline(
    db: AsyncSession, season_id: str, event_id: str | None, override: bool
) -> None:
    if override:
        return
    info = await deadline_info(db, season_id, event_id, can_override=False)
    if info["locked"]:
        raise ForbiddenError(
            "The paper submission deadline has passed "
            f"({info['deadline_date'].isoformat()}, {info['timezone']})"
        )


async def _assert_paper_deadline(db: AsyncSession, paper: Paper, override: bool) -> None:
    """The submission deadline governs the first submission. Revision rounds
    are opened by the organizers after that deadline; they are only blocked by
    a blocking official_final deadline."""
    if paper.revision_number <= 1:
        await _assert_before_deadline(db, paper.season_id, paper.event_id, override)
        return
    if override:
        return
    info = await deadline_info(db, paper.season_id, paper.event_id, can_override=False)
    if info["final_locked"]:
        raise ForbiddenError(
            "The official final submission deadline has passed "
            f"({info['final_deadline_date'].isoformat()}, {info['timezone']})"
        )


# ── Papers ────────────────────────────────────────────────────────────────────


def _paper_options():
    return (
        selectinload(Paper.assignments),
        selectinload(Paper.reviews),
        selectinload(Paper.versions),
    )


async def list_papers(
    db: AsyncSession,
    season_id: str | None = None,
    team_id: str | None = None,
    status: str | None = None,
    event_id: str | None = None,
    team_ids: set[str] | None = None,
) -> list[Paper]:
    """`team_ids`, when given, limits the result to those teams (mentor scoping)."""
    # Rows are re-read with populate_existing (see get_paper); flush first so
    # no pending change in this session is overwritten by the reload.
    await db.flush()
    q = (
        select(Paper)
        .options(*_paper_options())
        .order_by(Paper.created_at.desc())
        .execution_options(populate_existing=True)
    )
    if season_id:
        q = q.where(Paper.season_id == season_id)
    if team_id:
        q = q.where(Paper.team_id == team_id)
    if status:
        q = q.where(Paper.status == status)
    if event_id:
        q = q.where(Paper.event_id == event_id)
    if team_ids is not None:
        q = q.where(Paper.team_id.in_(team_ids))
    result = await db.execute(q)
    return list(result.scalars().all())


async def get_paper(db: AsyncSession, paper_id: str) -> Paper:
    # Versions, assignments and reviews are added as rows of their own, so an
    # already-loaded Paper would keep stale collections: reload them
    # (populate_existing), after flushing so no pending change is lost.
    await db.flush()
    result = await db.execute(
        select(Paper)
        .where(Paper.id == paper_id)
        .options(*_paper_options())
        .execution_options(populate_existing=True)
    )
    paper = result.scalar_one_or_none()
    if not paper:
        raise NotFoundError("Paper not found")
    return paper


async def create_paper(db: AsyncSession, data: dict, override_deadline: bool = False) -> Paper:
    data = data.copy()
    requested_event_id = data.get("event_id")
    await ensure_writable(db, season_id=data["season_id"])
    event = await resolve_event(db, data["season_id"], data.get("event_id"))
    await ensure_writable(db, event_id=event.id)
    data["event_id"] = event.id
    await _assert_before_deadline(db, data["season_id"], event.id, override_deadline)

    existing = await db.execute(
        select(Paper.id).where(
            Paper.season_id == data["season_id"], Paper.team_id == data["team_id"]
        )
    )
    if existing.scalar_one_or_none():
        raise ConflictError(
            "This team already has a paper for this season; upload a new version instead"
        )

    from modules.events.models import EventRegistration

    registration = await db.execute(
        select(EventRegistration.id).where(
            EventRegistration.event_id == event.id,
            EventRegistration.team_id == data["team_id"],
        )
    )
    if not registration.scalar_one_or_none():
        if requested_event_id:
            raise ConflictError("Team must be registered for the event before submitting a paper")
        from modules.events.service import ensure_legacy_default_registration

        await ensure_legacy_default_registration(db, event, data["team_id"])
    paper = Paper(**data)
    db.add(paper)
    try:
        async with db.begin_nested():
            await db.flush()
    except IntegrityError as exc:
        raise ConflictError("This team already has a paper for this season") from exc
    db.add(PaperStatusHistory(paper_id=paper.id, to_status="draft"))
    await db.flush()
    # Re-fetch with relationships eagerly loaded so response serialization
    # doesn't trigger a lazy load (MissingGreenlet) in the async context.
    return await get_paper(db, paper.id)


async def update_paper(db: AsyncSession, paper_id: str, **kwargs) -> Paper:
    paper = await get_paper(db, paper_id)
    await ensure_paper_writable(db, paper)
    for key, value in kwargs.items():
        if value is not None:
            setattr(paper, key, value)
    await db.flush()
    return await get_paper(db, paper_id)


# ── Versions ──────────────────────────────────────────────────────────────────


async def add_version(
    db: AsyncSession,
    paper_id: str,
    file: UploadFile,
    uploaded_by: str | None,
    override_deadline: bool = False,
) -> Paper:
    """Store an upload as the paper's next version.

    Only drafts and papers sent back for revision take new files: once a
    version is submitted it is what the reviewers judge.
    """
    paper = await get_paper(db, paper_id)
    await ensure_paper_writable(db, paper)
    if paper.status not in EDITABLE_STATUSES:
        raise ConflictError(f"No new version can be uploaded while the paper is '{paper.status}'")
    await _assert_paper_deadline(db, paper, override_deadline)

    number = (paper.current_version or 0) + 1
    file_path, file_name, size = await save_file(file, paper_id, number)
    storage_path = Path(file_path).relative_to(Path(settings.upload_dir).resolve()).as_posix()
    db.add(
        PaperVersion(
            paper_id=paper.id,
            version_number=number,
            revision_number=paper.revision_number,
            file_name=file_name,
            storage_path=storage_path,
            file_size_bytes=size,
            uploaded_by=uploaded_by,
        )
    )
    paper.current_version = number
    paper.file_name = file_name
    paper.file_size_bytes = size
    paper.file_url = f"/api/papers/{paper.id}/download"
    try:
        async with db.begin_nested():
            await db.flush()
    except IntegrityError as exc:
        Path(file_path).unlink(missing_ok=True)
        raise ConflictError("Another upload finished first; please retry") from exc
    return await get_paper(db, paper.id)


def resolve_version_file(paper: Paper, version_number: int | None) -> tuple[Path, str]:
    """Absolute path and file name of one version (default: the latest)."""
    wanted = version_number if version_number is not None else paper.current_version
    version = next((v for v in paper.versions if v.version_number == wanted), None)
    if version is None:
        if version_number is not None:
            raise NotFoundError(f"Version {version_number} not found")
        raise NotFoundError("No file uploaded")
    base = Path(settings.upload_dir)
    path = ensure_within(base, base / version.storage_path)
    if not path.is_file():
        raise NotFoundError("File missing on disk")
    return path, safe_filename(version.file_name, "paper.pdf")


# ── Status workflow ───────────────────────────────────────────────────────────


async def _team_user_ids(db: AsyncSession, team_id: str) -> list[str]:
    """Accounts linked to the paper's team: the only recipients of its news."""
    from modules.teams.models import TeamMember

    result = await db.execute(
        select(TeamMember.user_id).where(
            TeamMember.team_id == team_id, TeamMember.user_id.isnot(None)
        )
    )
    return [uid for uid in result.scalars().all() if uid]


async def _record_status(
    db: AsyncSession,
    paper: Paper,
    status: str,
    changed_by: str | None,
    reason: str | None = None,
) -> None:
    db.add(
        PaperStatusHistory(
            paper_id=paper.id,
            from_status=paper.status,
            to_status=status,
            reason=reason,
            changed_by=changed_by,
        )
    )
    paper.status = status
    await emit_event(
        db,
        "paper_status_changed",
        event_id=paper.event_id,
        payload={
            "paperId": paper.id,
            "status": status,
            "message": f"Paper status: {status}",
            "userIds": await _team_user_ids(db, paper.team_id),
        },
    )


async def submit_paper(
    db: AsyncSession, paper_id: str, submitted_by: str, override_deadline: bool = False
) -> Paper:
    """Hand the latest version in for review.

    A first submission becomes "submitted"; a revision becomes "resubmitted"
    and puts every reviewer back to "pending" for the new version.
    """
    paper = await get_paper(db, paper_id)
    await ensure_paper_writable(db, paper)
    if paper.status not in EDITABLE_STATUSES:
        raise ConflictError("Paper cannot be submitted in its current state")
    if not paper.current_version:
        raise ConflictError("Upload the paper as PDF before submitting it")
    await _assert_paper_deadline(db, paper, override_deadline)

    now = datetime.now(UTC)
    new_status = "resubmitted" if paper.status == "revision_requested" else "submitted"
    paper.submitted_at = now
    paper.submitted_by = submitted_by
    for version in paper.versions:
        if version.version_number == paper.current_version:
            version.submitted_at = now
    for assignment in paper.assignments:
        assignment.status = "pending"
        assignment.version_number = paper.current_version
        assignment.completed_at = None
        assignment.reminder_sent_at = None
    await _record_status(db, paper, new_status, submitted_by)
    await db.flush()
    return await get_paper(db, paper.id)


async def set_paper_status(
    db: AsyncSession,
    paper_id: str,
    status: str,
    changed_by: str | None = None,
    reason: str | None = None,
) -> Paper:
    """Organizer override of the status.

    revision_requested opens a new review round; disqualified_ai (AI misuse)
    zeroes the score and closes the paper for good.
    """
    paper = await get_paper(db, paper_id)
    await ensure_paper_writable(db, paper)
    if paper.status == status and status != "revision_requested":
        return paper
    if status == "revision_requested":
        paper.revision_number += 1
        paper.finalized_at = None
    await _record_status(db, paper, status, changed_by, reason)
    if status == "disqualified_ai":
        paper.final_score = 0.0
        paper.finalized_at = datetime.now(UTC)
        await db.flush()
        await _recompute_paper_ranks(db, paper.season_id)
    await db.flush()
    return await get_paper(db, paper.id)


# ── Reviewer assignments ──────────────────────────────────────────────────────


async def _assert_reviewer_eligible(db: AsyncSession, paper: Paper, reviewer_id: str) -> None:
    from core.auth import has_elevated_access
    from modules.auth.models import User
    from modules.teams.models import Team, TeamMember

    reviewer = await db.get(User, reviewer_id)
    if not reviewer or not reviewer.is_active:
        raise NotFoundError("Reviewer not found")
    if not await has_elevated_access(db, reviewer, "papers:review"):
        raise ValidationError(f"{reviewer.display_name} does not hold the papers:review permission")

    reviewer_team_ids = set(
        (
            await db.execute(select(TeamMember.team_id).where(TeamMember.user_id == reviewer_id))
        ).scalars()
    )
    if paper.team_id in reviewer_team_ids:
        raise ConflictError(
            f"Conflict of interest: {reviewer.display_name} is a member of the paper's team"
        )
    paper_team = await db.get(Team, paper.team_id)
    school = (paper_team.school or "").strip().casefold() if paper_team else ""
    if school and reviewer_team_ids:
        schools = (
            await db.execute(select(Team.school).where(Team.id.in_(reviewer_team_ids)))
        ).scalars()
        if any((s or "").strip().casefold() == school for s in schools):
            raise ConflictError(
                f"Conflict of interest: {reviewer.display_name} belongs to a team of the "
                f"same school ({paper_team.school if paper_team else ''})"
            )


async def assign_reviewer(
    db: AsyncSession,
    paper_id: str,
    reviewer_id: str,
    assigned_by: str,
    due_at: datetime | None = None,
) -> ReviewerAssignment:
    paper = await get_paper(db, paper_id)
    await ensure_paper_writable(db, paper)
    if paper.status in _CLOSED_STATUSES:
        raise ConflictError("The review of this paper is closed")
    existing = await db.execute(
        select(ReviewerAssignment).where(
            ReviewerAssignment.paper_id == paper_id,
            ReviewerAssignment.reviewer_id == reviewer_id,
        )
    )
    if existing.scalar_one_or_none():
        raise ConflictError("Reviewer already assigned")
    await _assert_reviewer_eligible(db, paper, reviewer_id)

    assignment = ReviewerAssignment(
        paper_id=paper_id,
        reviewer_id=reviewer_id,
        assigned_by=assigned_by,
        due_at=due_at,
        status="pending",
        version_number=paper.current_version,
    )
    db.add(assignment)
    # The review starts with the first reviewer, not when all have finished.
    if paper.status in ("submitted", "resubmitted"):
        await _record_status(db, paper, "under_review", assigned_by)
    await db.flush()
    await emit_event(
        db,
        "reviewer_assigned",
        event_id=paper.event_id,
        payload={
            "paperId": paper_id,
            "userId": reviewer_id,
            "message": f"You were assigned to review: {paper.title}",
        },
    )
    return assignment


# ── Reviews ───────────────────────────────────────────────────────────────────


async def get_or_create_review(
    db: AsyncSession,
    paper_id: str,
    reviewer_id: str,
    revision_number: int,
    version_number: int | None = None,
) -> PaperReview:
    result = await db.execute(
        select(PaperReview).where(
            PaperReview.paper_id == paper_id,
            PaperReview.reviewer_id == reviewer_id,
            PaperReview.revision_number == revision_number,
        )
    )
    review = result.scalar_one_or_none()
    if not review:
        review = PaperReview(
            paper_id=paper_id,
            reviewer_id=reviewer_id,
            revision_number=revision_number,
            version_number=version_number,
        )
        db.add(review)
        await db.flush()
        await db.refresh(review)
    return review


def _criterion_scores(review: PaperReview) -> list[float | None]:
    return [getattr(review, f"score_{name}") for name in REVIEW_CRITERIA]


async def save_review(
    db: AsyncSession,
    paper_id: str,
    reviewer_id: str,
    data: dict,
    submit: bool = False,
) -> PaperReview:
    paper = await get_paper(db, paper_id)
    await ensure_paper_writable(db, paper)

    assignment_row = (
        await db.execute(
            select(ReviewerAssignment).where(
                ReviewerAssignment.paper_id == paper_id,
                ReviewerAssignment.reviewer_id == reviewer_id,
            )
        )
    ).scalar_one_or_none()
    if not assignment_row:
        raise ForbiddenError("Not assigned to review this paper")
    if paper.status not in REVIEWABLE_STATUSES or paper.finalized_at is not None:
        raise ConflictError("This paper is not open for review")

    review = await get_or_create_review(
        db, paper_id, reviewer_id, paper.revision_number, paper.current_version
    )
    if review.is_submitted:
        raise ConflictError("Review already submitted; an organizer has to reopen it first")
    if review.version_number is None:
        review.version_number = paper.current_version

    for key, value in data.items():
        if value is not None:
            setattr(review, key, value)

    scores = _criterion_scores(review)
    valid_scores = [s for s in scores if s is not None]
    review.total_score = round(sum(valid_scores) / len(valid_scores), 2) if valid_scores else None

    if assignment_row.status == "pending":
        assignment_row.status = "in_progress"
    # A reviewer starting work also counts as the review having begun.
    if paper.status in ("submitted", "resubmitted"):
        await _record_status(db, paper, "under_review", reviewer_id)

    if submit:
        missing = [name for name, s in zip(REVIEW_CRITERIA, scores, strict=True) if s is None]
        if missing:
            raise ValidationError(f"Score every criterion before submitting: {', '.join(missing)}")
        if not review.recommendation:
            raise ValidationError("Choose a recommendation before submitting")
        review.is_submitted = True
        review.submitted_at = datetime.now(UTC)
        assignment_row.status = "completed"
        assignment_row.completed_at = review.submitted_at

    await db.flush()
    return review


async def reopen_review(db: AsyncSession, paper_id: str, review_id: str) -> PaperReview:
    """Organizer unlocks a submitted review so its reviewer can amend it."""
    paper = await get_paper(db, paper_id)
    await ensure_paper_writable(db, paper)
    review = next((r for r in paper.reviews if r.id == review_id), None)
    if review is None:
        raise NotFoundError("Review not found")
    if (
        review.revision_number != paper.revision_number
        or paper.status not in REVIEWABLE_STATUSES
        or paper.finalized_at is not None
    ):
        raise ConflictError("Reviews of a decided or finalized round stay locked")
    review.is_submitted = False
    review.submitted_at = None
    for assignment in paper.assignments:
        if assignment.reviewer_id == review.reviewer_id:
            assignment.status = "in_progress"
            assignment.completed_at = None
    await db.flush()
    return review


def team_feedback(paper: Paper) -> list[PaperReview]:
    """Submitted reviews the team may read.

    A round's feedback is released once the organizers decided on it: earlier
    rounds always (a revision was requested), the current one only in a
    decided status. Drafts never.
    """
    decided = paper.status in DECIDED_STATUSES
    return sorted(
        (
            r
            for r in paper.reviews
            if r.is_submitted
            and (
                r.revision_number < paper.revision_number
                or (r.revision_number == paper.revision_number and decided)
            )
        ),
        key=lambda r: (r.revision_number, r.submitted_at or r.created_at),
    )


# ── Finalization & ranking ────────────────────────────────────────────────────


async def _recompute_paper_ranks(db: AsyncSession, season_id: str) -> None:
    """Rank papers in a season by final_score DESC; papers without a score get no rank."""
    scored = await db.execute(
        select(Paper)
        .where(Paper.season_id == season_id, Paper.final_score.isnot(None))
        .order_by(Paper.final_score.desc())
    )
    for i, p in enumerate(scored.scalars().all(), start=1):
        p.paper_rank = i
    unscored = await db.execute(
        select(Paper).where(Paper.season_id == season_id, Paper.final_score.is_(None))
    )
    for p in unscored.scalars().all():
        p.paper_rank = None


def compute_final_score(paper: Paper) -> float | None:
    """0-1 score of the current round.

    Mean of the submitted reviews' totals (each the mean of the five criteria,
    0-10) divided by 10, minus the format deduction (points on the 0-100
    scale), clamped to 0-1. AI misuse is always 0.
    """
    if paper.status == "disqualified_ai":
        return 0.0
    totals = [
        r.total_score
        for r in paper.reviews
        if r.is_submitted
        and r.revision_number == paper.revision_number
        and r.total_score is not None
    ]
    if not totals:
        return None
    base = sum(totals) / len(totals) / 10.0
    score = base - (paper.format_deduction or 0.0) / 100.0
    return round(min(1.0, max(0.0, score)), 4)


async def finalize_paper(db: AsyncSession, paper_id: str) -> Paper:
    """Aggregate the current round into final_score, lock its reviews and
    recompute the season ranking."""
    paper = await get_paper(db, paper_id)
    await ensure_paper_writable(db, paper)
    paper.final_score = compute_final_score(paper)
    paper.finalized_at = datetime.now(UTC)
    await db.flush()
    await _recompute_paper_ranks(db, paper.season_id)
    await db.flush()
    return await get_paper(db, paper_id)


async def list_status_history(db: AsyncSession, paper_id: str) -> list[PaperStatusHistory]:
    await get_paper(db, paper_id)
    result = await db.execute(
        select(PaperStatusHistory)
        .where(PaperStatusHistory.paper_id == paper_id)
        .order_by(PaperStatusHistory.changed_at)
    )
    return list(result.scalars().all())


# ── Statistics ────────────────────────────────────────────────────────────────


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 4) if values else None


async def paper_stats(
    db: AsyncSession, season_id: str | None = None, event_id: str | None = None
) -> dict:
    papers = await list_papers(db, season_id=season_id, event_id=event_id)
    by_status: dict[str, int] = {}
    for p in papers:
        by_status[p.status] = by_status.get(p.status, 0) + 1
    accepted = by_status.get("accepted", 0)
    rejected = by_status.get("rejected", 0)
    disqualified = by_status.get("disqualified_ai", 0)
    decided = accepted + rejected + disqualified

    reviews = [r for p in papers for r in p.reviews]
    submitted = [r for r in reviews if r.is_submitted]
    open_assignments = sum(
        1 for p in papers for a in p.assignments if a.status not in ("completed",)
    )
    return {
        "total": len(papers),
        "by_status": by_status,
        "decided": decided,
        "accepted": accepted,
        "rejected": rejected,
        "disqualified": disqualified,
        "acceptance_rate": round(accepted / decided, 4) if decided else None,
        "average_final_score": _mean([p.final_score for p in papers if p.final_score is not None]),
        "average_review_score": _mean(
            [r.total_score for r in submitted if r.total_score is not None]
        ),
        "criterion_averages": {
            name: _mean(
                [
                    getattr(r, f"score_{name}")
                    for r in submitted
                    if getattr(r, f"score_{name}") is not None
                ]
            )
            for name in REVIEW_CRITERIA
        },
        "reviews_submitted": len(submitted),
        "reviews_open": open_assignments,
        "average_revision_rounds": _mean(
            [float(p.revision_number) for p in papers if p.status != "draft"]
        ),
    }


async def reviewer_workload(db: AsyncSession, event_id: str | None = None) -> list[dict]:
    query = select(ReviewerAssignment).join(Paper)
    if event_id:
        query = query.where(Paper.event_id == event_id)
    assignments = list((await db.execute(query)).scalars().all())
    now = datetime.now(UTC)
    workloads: dict[str, dict] = {}
    for assignment in assignments:
        item = workloads.setdefault(
            assignment.reviewer_id,
            {
                "reviewer_id": assignment.reviewer_id,
                "assigned": 0,
                "open": 0,
                "overdue": 0,
                "completed": 0,
            },
        )
        item["assigned"] += 1
        if assignment.status == "completed":
            item["completed"] += 1
        else:
            item["open"] += 1
            due_at = assignment.due_at
            if due_at and due_at.tzinfo is None:
                due_at = due_at.replace(tzinfo=UTC)
            if due_at and due_at < now:
                item["overdue"] += 1
    return list(workloads.values())


async def mark_reminder_sent(
    db: AsyncSession, paper_id: str, assignment_id: str
) -> ReviewerAssignment:
    result = await db.execute(
        select(ReviewerAssignment).where(
            ReviewerAssignment.id == assignment_id,
            ReviewerAssignment.paper_id == paper_id,
        )
    )
    assignment = result.scalar_one_or_none()
    if not assignment:
        raise NotFoundError("Reviewer assignment not found")
    if assignment.status == "completed":
        raise ConflictError("Completed reviews do not need reminders")
    assignment.reminder_sent_at = datetime.now(UTC)
    paper = await get_paper(db, paper_id)
    await emit_event(
        db,
        "review_reminder",
        event_id=paper.event_id,
        payload={
            "paperId": paper_id,
            "userId": assignment.reviewer_id,
            "message": f"Review reminder: {paper.title}",
        },
    )
    return assignment
