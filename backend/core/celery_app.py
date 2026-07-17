"""Celery worker configuration for OCR and recurring device polling."""

from celery import Celery

from core.config import get_settings

settings = get_settings()
celery_app = Celery(
    "botball_dashboard",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["modules.scoring.score_sheets.tasks"],
)
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
