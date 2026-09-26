"""Periodic due-date processing for reviewer assignments."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from core.celery_app import celery_app, run_task
from core.database import WorkerSessionLocal
from modules.paper_review.models import REVIEWABLE_STATUSES, Paper, ReviewerAssignment
from modules.paper_review.service import mark_reminder_sent
from modules.seasons.lifecycle import ARCHIVED
from modules.seasons.models import Season


@celery_app.task(name="papers.process_review_deadlines")
def process_review_deadlines() -> None:
    async def run() -> None:
        async with WorkerSessionLocal() as db:
            now = datetime.now(UTC)
            reminder_cutoff = now - timedelta(hours=24)
            # Only papers still in review: once organisers decide a paper
            # (possibly before every reviewer finished), an open assignment
            # is moot and must not be marked overdue or reminded daily.
            result = await db.execute(
                select(ReviewerAssignment)
                .join(Paper, Paper.id == ReviewerAssignment.paper_id)
                .join(Season, Season.id == Paper.season_id)
                .where(
                    ReviewerAssignment.status != "completed",
                    ReviewerAssignment.due_at.is_not(None),
                    ReviewerAssignment.due_at <= now + timedelta(hours=24),
                    Paper.status.in_(REVIEWABLE_STATUSES),
                    Season.status != ARCHIVED,
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

    run_task(run)


@celery_app.task(name="papers.deadline_reminders")
def paper_deadline_reminders() -> None:
    """Remind teams (and reviewers) 7, 3 and 1 day(s) before paper deadlines."""
    from modules.paper_review.deadlines import queue_paper_deadline_reminders

    async def run() -> None:
        async with WorkerSessionLocal() as db:
            await queue_paper_deadline_reminders(db)
            await db.commit()

    run_task(run)
