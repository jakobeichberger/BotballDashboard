"""Celery worker configuration for OCR and recurring device polling.

Queues
------
``ocr``       score-sheet OCR (template extraction, scans): seconds to minutes
              of CPU per job.
``periodic``  the beat schedule below: short, frequent housekeeping.
``default``   anything else.

OCR runs in its own worker (docker-compose service ``worker-ocr``) so a
stack of uploaded scans can never delay notifications or printer polling;
the ``worker`` service consumes ``default`` and ``periodic``. Every beat
entry expires: when the workers are behind, a run that is superseded by the
next one is dropped instead of piling up.
"""

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

from celery import Celery
from celery.schedules import crontab

from core.config import get_settings

DEFAULT_QUEUE = "default"
PERIODIC_QUEUE = "periodic"
OCR_QUEUE = "ocr"

settings = get_settings()
celery_app = Celery(
    "botball_dashboard",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "modules.scoring.score_sheets.tasks",
        "modules.printing.tasks",
        "modules.dashboard.tasks",
        "modules.paper_review.tasks",
    ],
)


def _periodic(task: str, schedule, expires: float) -> dict:
    return {
        "task": task,
        "schedule": schedule,
        "options": {"queue": PERIODIC_QUEUE, "expires": expires},
    }


celery_app.conf.beat_schedule = {
    "poll-printers": _periodic("printing.poll_printers", 15.0, expires=15),
    "deliver-notification-outbox": _periodic("notifications.deliver_outbox", 10.0, expires=10),
    "queue-match-reminders": _periodic("notifications.match_reminders", 60.0, expires=60),
    # Daily at 07:00 UTC, before the morning of the event day in Europe.
    "queue-deadline-reminders": _periodic(
        "notifications.deadline_reminders", crontab(hour=7, minute=0), expires=3600
    ),
    # Daily, right after the season deadline reminders.
    "queue-paper-deadline-reminders": _periodic(
        "papers.deadline_reminders", crontab(hour=7, minute=5), expires=3600
    ),
    "process-paper-review-deadlines": _periodic(
        "papers.process_review_deadlines", 3600.0, expires=3600
    ),
    # Delivered outbox history older than 30 days (modules.dashboard.tasks).
    "cleanup-notification-outbox": _periodic(
        "notifications.cleanup_outbox", crontab(hour=3, minute=17), expires=3600
    ),
}
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_time_limit=300,
    broker_connection_retry_on_startup=True,
    task_default_queue=DEFAULT_QUEUE,
    task_routes={
        "score_sheets.*": {"queue": OCR_QUEUE},
        "printing.poll_printers": {"queue": PERIODIC_QUEUE},
        "notifications.*": {"queue": PERIODIC_QUEUE},
        "papers.*": {"queue": PERIODIC_QUEUE},
    },
)

T = TypeVar("T")


def run_task(main: Callable[[], Awaitable[T]]) -> T:
    """Run one task's coroutine in a fresh event loop.

    Tasks use core.database.WorkerSessionLocal (no connection pool, see
    there). Live events queued with publish_after_commit are sent from
    after-commit hooks as background tasks; they are awaited here, since
    asyncio.run cancels whatever is still pending when the task returns.
    The loop's Redis clients are closed with it.
    """

    async def runner() -> T:
        from core.live import drain_pending_publishes
        from core.redis_client import close_clients

        try:
            return await main()
        finally:
            await drain_pending_publishes()
            await close_clients()

    return asyncio.run(runner())
