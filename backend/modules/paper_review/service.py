import os
from datetime import datetime, timezone
from pathlib import Path

import aiofiles
from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.config import get_settings
from core.exceptions import ConflictError, ForbiddenError, NotFoundError
from modules.paper_review.models import Paper, PaperReview, ReviewerAssignment

settings = get_settings()


async def save_file(file: UploadFile, paper_id: str) -> tuple[str, str, int]:
    upload_dir = Path(settings.upload_dir) / "papers" / paper_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_path = upload_dir / (file.filename or "paper.pdf")

    content = await file.read()
    async with aiofiles.open(file_path, "wb") as f:
        await f.write(content)

    return str(file_path), file.filename or "paper.pdf", len(content)


async def list_papers(
    db: AsyncSession,
    season_id: str | None = None,
    team_id: str | None = None,
    status: str | None = None,
) -> list[Paper]:
    q = select(Paper).options(
        selectinload(Paper.assignments)
    ).order_by(Paper.created_at.desc())
    if season_id:
        q = q.where(Paper.season_id == season_id)
    if team_id:
        q = q.where(Paper.team_id == team_id)
    if status:
        q = q.where(Paper.status == status)
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
    paper = Paper(**data)
    db.add(paper)
    return paper


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
    paper.submitted_at = datetime.now(timezone.utc)
    paper.submitted_by = submitted_by
    return paper


async def set_paper_status(db: AsyncSession, paper_id: str, status: str) -> Paper:
    paper = await get_paper(db, paper_id)
    paper.status = status
    if status == "revision_requested":
        paper.revision_number += 1
    return paper


async def assign_reviewer(
    db: AsyncSession, paper_id: str, reviewer_id: str, assigned_by: str
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
        paper_id=paper_id, reviewer_id=reviewer_id, assigned_by=assigned_by
    )
    db.add(assignment)
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
    if not assignment.scalar_one_or_none():
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
        review.submitted_at = datetime.now(timezone.utc)
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
            paper.status = "under_review"

    return review
