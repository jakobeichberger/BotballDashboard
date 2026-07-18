"""Periodic due-date processing for reviewer assignments."""

import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from core.celery_app import celery_app
from core.database import AsyncSessionLocal
from modules.paper_review.models import ReviewerAssignment
from modules.paper_review.service import mark_reminder_sent


@celery_app.task(name="papers.process_review_deadlines")
def process_review_deadlines() -> None:
    async def run() -> None:
        async with AsyncSessionLocal() as db:
            now = datetime.now(UTC)
            reminder_cutoff = now - timedelta(hours=24)
            result = await db.execute(
                select(ReviewerAssignment).where(
                    ReviewerAssignment.status != "completed",
                    ReviewerAssignment.due_at.is_not(None),
                    ReviewerAssignment.due_at <= now + timedelta(hours=24),
                )
            )
            for assignment in result.scalars().all():
                if assignment.due_at and assignment.due_at < now:
                    assignment.status = "overdue"
                if (
                    assignment.reminder_sent_at is None
                    or assignment.reminder_sent_at < reminder_cutoff
                ):
                    await mark_reminder_sent(db, assignment.paper_id, assignment.id)
            await db.commit()

    asyncio.run(run())
