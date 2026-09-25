"""Celery worker configuration for OCR and recurring device polling."""

from contextlib import suppress
from pathlib import Path

from celery import Celery
from celery.schedules import crontab
from celery.signals import after_task_publish, beat_init, setup_logging

from core.config import get_settings
from core.logging import configure_logging

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
celery_app.conf.beat_schedule = {
    "poll-printers": {
        "task": "printing.poll_printers",
        "schedule": 15.0,
    },
    "deliver-notification-outbox": {
        "task": "notifications.deliver_outbox",
        "schedule": 10.0,
    },
    "queue-match-reminders": {
        "task": "notifications.match_reminders",
        "schedule": 60.0,
    },
    "queue-deadline-reminders": {
        "task": "notifications.deadline_reminders",
        # Daily at 07:00 UTC, before the morning of the event day in Europe.
        "schedule": crontab(hour=7, minute=0),
    },
    "queue-paper-deadline-reminders": {
        "task": "papers.deadline_reminders",
        # Daily, right after the season deadline reminders.
        "schedule": crontab(hour=7, minute=5),
    },
    "process-paper-review-deadlines": {
        "task": "papers.process_review_deadlines",
        "schedule": 3600.0,
    },
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
)


@setup_logging.connect
def _configure_worker_logging(**_kwargs) -> None:
    """Worker and beat log through structlog like the API (JSON in production).

    Connecting this signal also stops Celery from installing its own root
    handler, so every record is formatted once.
    """
    configure_logging()


# Celery beat has no ping. Beat touches this file whenever the broker accepted
# one of its tasks (the notification outbox is due every 10 s), and the beat
# container's healthcheck (scripts/beat_healthcheck.py) checks its age.
BEAT_HEARTBEAT_FILE = Path("/tmp/celerybeat-heartbeat")
_beat_running = False


@beat_init.connect
def _mark_beat_process(**_kwargs) -> None:
    global _beat_running
    _beat_running = True


@after_task_publish.connect
def _beat_heartbeat(**_kwargs) -> None:
    # The API and the worker publish tasks too; only beat keeps the heartbeat.
    if _beat_running:
        with suppress(OSError):
            BEAT_HEARTBEAT_FILE.touch()
