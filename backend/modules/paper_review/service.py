from datetime import UTC, datetime
from pathlib import Path

import aiofiles
from fastapi import HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.config import get_settings
from core.domain_events import emit_event
from core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from core.files import ensure_within, safe_filename
from modules.paper_review.models import (
    Paper,
    PaperReview,
    PaperStatusHistory,
    ReviewerAssignment,
)
from modules.scoring.service import resolve_event

settings = get_settings()


async def save_file(file: UploadFile, paper_id: str) -> tuple[str, str, int]:
    if file.content_type and file.content_type not in (
        "application/pdf",
        "application/octet-stream",
    ):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    upload_dir = Path(settings.upload_dir) / "papers" / paper_id
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


async def list_papers(
    db: AsyncSession,
    season_id: str | None = None,
    team_id: str | None = None,
    status: str | None = None,
    event_id: str | None = None,
) -> list[Paper]:
    q = (
        select(Paper)
        .options(
            selectinload(Paper.assignments),
            selectinload(Paper.reviews),
        )
        .order_by(Paper.created_at.desc())
    )
    if season_id:
        q = q.where(Paper.season_id == season_id)
    if team_id:
        q = q.where(Paper.team_id == team_id)
    if status:
        q = q.where(Paper.status == status)
    if event_id:
        q = q.where(Paper.event_id == event_id)
    result = await db.execute(q)
    return list(result.scalars().all())


async def get_paper(db: AsyncSession, paper_id: str) -> Paper:
    result = await db.execute(
        select(Paper)
        .where(Paper.id == paper_id)
        .options(selectinload(Paper.reviews), selectinload(Paper.assignments))
    )
    paper = result.scalar_one_or_none()
    if not paper:
        raise NotFoundError("Paper not found")
    return paper


async def create_paper(db: AsyncSession, data: dict) -> Paper:
    data = data.copy()
    requested_event_id = data.get("event_id")
    event = await resolve_event(db, data["season_id"], data.get("event_id"))
    data["event_id"] = event.id
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
    await db.flush()
    db.add(PaperStatusHistory(paper_id=paper.id, to_status="draft"))
    await db.flush()
    # Re-fetch with relationships eagerly loaded so response serialization
    # doesn't trigger a lazy load (MissingGreenlet) in the async context.
    return await get_paper(db, paper.id)


async def update_paper(db: AsyncSession, paper_id: str, **kwargs) -> Paper:
    paper = await get_paper(db, paper_id)
    for key, value in kwargs.items():
        if value is not None:
            setattr(paper, key, value)
    return paper


async def submit_paper(db: AsyncSession, paper_id: str, submitted_by: str) -> Paper:
    paper = await get_paper(db, paper_id)
    if paper.status not in ("draft", "revision_requested"):
        raise ConflictError("Paper cannot be submitted in its current state")
    paper.status = "submitted"
    paper.submitted_at = datetime.now(UTC)
    paper.submitted_by = submitted_by
    db.add(
        PaperStatusHistory(
            paper_id=paper.id,
            from_status="draft" if paper.revision_number == 1 else "revision_requested",
            to_status="submitted",
            changed_by=submitted_by,
        )
    )
    await emit_event(
        db,
        "paper_status_changed",
        event_id=paper.event_id,
        payload={
            "paperId": paper.id,
            "status": "submitted",
            "message": "Paper status: submitted",
        },
    )
    await db.flush()
    return await get_paper(db, paper.id)


async def set_paper_status(
    db: AsyncSession,
    paper_id: str,
    status: str,
    changed_by: str | None = None,
    reason: str | None = None,
) -> Paper:
    paper = await get_paper(db, paper_id)
    old_status = paper.status
    if old_status == status and status != "revision_requested":
        return paper
    paper.status = status
    if status == "revision_requested":
        paper.revision_number += 1
    db.add(
        PaperStatusHistory(
            paper_id=paper.id,
            from_status=old_status,
            to_status=status,
            reason=reason,
            changed_by=changed_by,
        )
    )
    await emit_event(
        db,
        "paper_status_changed",
        event_id=paper.event_id,
        payload={"paperId": paper.id, "status": status, "message": f"Paper status: {status}"},
    )
    await db.flush()
    return await get_paper(db, paper.id)


async def assign_reviewer(
    db: AsyncSession,
    paper_id: str,
    reviewer_id: str,
    assigned_by: str,
    due_at: datetime | None = None,
) -> ReviewerAssignment:
    await get_paper(db, paper_id)
    existing = await db.execute(
        select(ReviewerAssignment).where(
            ReviewerAssignment.paper_id == paper_id,
            ReviewerAssignment.reviewer_id == reviewer_id,
        )
    )
    if existing.scalar_one_or_none():
        raise ConflictError("Reviewer already assigned")

    assignment = ReviewerAssignment(
        paper_id=paper_id,
        reviewer_id=reviewer_id,
        assigned_by=assigned_by,
        due_at=due_at,
    )
    db.add(assignment)
    await db.flush()
    paper = await get_paper(db, paper_id)
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


async def get_or_create_review(
    db: AsyncSession, paper_id: str, reviewer_id: str, revision_number: int
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
        )
        db.add(review)
        await db.flush()
        await db.refresh(review)
    return review


async def save_review(
    db: AsyncSession,
    paper_id: str,
    reviewer_id: str,
    data: dict,
    submit: bool = False,
) -> PaperReview:
    paper = await get_paper(db, paper_id)

    # Verify assignment
    assignment = await db.execute(
        select(ReviewerAssignment).where(
            ReviewerAssignment.paper_id == paper_id,
            ReviewerAssignment.reviewer_id == reviewer_id,
        )
    )
    assignment_row = assignment.scalar_one_or_none()
    if not assignment_row:
        raise ForbiddenError("Not assigned to review this paper")

    review = await get_or_create_review(db, paper_id, reviewer_id, paper.revision_number)

    for key, value in data.items():
        if value is not None:
            setattr(review, key, value)

    # Calculate total score
    scores = [
        review.score_content,
        review.score_methodology,
        review.score_presentation,
        review.score_originality,
    ]
    valid_scores = [s for s in scores if s is not None]
    if valid_scores:
        review.total_score = round(sum(valid_scores) / len(valid_scores), 2)

    if submit:
        review.is_submitted = True
        review.submitted_at = datetime.now(UTC)
        assignment_row.status = "completed"
        assignment_row.completed_at = review.submitted_at
        # Flush so the just-submitted review is counted below (autoflush is off).
        await db.flush()
        # If all reviewers submitted → transition paper to under_review
        assignments = await db.execute(
            select(ReviewerAssignment).where(ReviewerAssignment.paper_id == paper_id)
        )
        assignment_count = len(assignments.scalars().all())
        submitted_reviews = await db.execute(
            select(PaperReview).where(
                PaperReview.paper_id == paper_id,
                PaperReview.is_submitted == True,
                PaperReview.revision_number == paper.revision_number,
            )
        )
        if len(submitted_reviews.scalars().all()) >= assignment_count > 0:
            old_status = paper.status
            paper.status = "under_review"
            db.add(
                PaperStatusHistory(
                    paper_id=paper.id,
                    from_status=old_status,
                    to_status="under_review",
                    changed_by=reviewer_id,
                )
            )

    return review


async def list_status_history(db: AsyncSession, paper_id: str) -> list[PaperStatusHistory]:
    await get_paper(db, paper_id)
    result = await db.execute(
        select(PaperStatusHistory)
        .where(PaperStatusHistory.paper_id == paper_id)
        .order_by(PaperStatusHistory.changed_at)
    )
    return list(result.scalars().all())


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
            if assignment.due_at and assignment.due_at < now:
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
