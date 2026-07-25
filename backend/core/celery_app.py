"""Celery worker configuration for OCR and recurring device polling."""

from celery import Celery

from core.config import get_settings

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
