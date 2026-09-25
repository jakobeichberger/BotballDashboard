"""Queue Celery tasks only once the database transaction has committed.

A task queued before the commit can reach a worker before the row it works on
exists (the worker then finds nothing and the record stays "queued"), and a
rolled-back request would still have queued work. ``enqueue_after_commit``
collects tasks on the session and sends them from its ``after_commit`` hook;
a rollback drops them. ``Task.delay`` talks to the broker synchronously, so it
runs in a worker thread instead of blocking the event loop.
"""

import asyncio
from typing import Any

from kombu.exceptions import KombuError
from redis.exceptions import RedisError
from sqlalchemy import event as sa_event
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from core.logging import get_logger

logger = get_logger("task_queue")

_PENDING_KEY = "celery_tasks_pending"
_HOOKED_KEY = "celery_tasks_hooked"
# Strong references to in-flight sends (the loop only keeps weak ones).
_inflight: set[asyncio.Task] = set()


def enqueue_after_commit(db: AsyncSession | Session, task: Any, *args: Any) -> None:
    """Call ``task.delay(*args)`` after the session's transaction commits."""
    session = db.sync_session if isinstance(db, AsyncSession) else db
    session.info.setdefault(_PENDING_KEY, []).append((task, args))
    if not session.info.get(_HOOKED_KEY):
        sa_event.listen(session, "after_commit", _after_commit)
        sa_event.listen(session, "after_rollback", _after_rollback)
        session.info[_HOOKED_KEY] = True


def _after_rollback(session: Session) -> None:
    session.info.pop(_PENDING_KEY, None)


def _after_commit(session: Session) -> None:
    pending = session.info.pop(_PENDING_KEY, None)
    if not pending:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # A synchronous session outside an event loop (scripts): send inline.
        for task, args in pending:
            _send(task, args)
        return
    job = loop.create_task(_send_all(pending))
    _inflight.add(job)
    job.add_done_callback(_inflight.discard)


def _send(task: Any, args: tuple) -> None:
    try:
        task.delay(*args)
    except (KombuError, RedisError, OSError) as exc:
        # The record stays queued; its retry endpoint can queue it again.
        logger.warning("task_enqueue_failed", task=getattr(task, "name", str(task)), error=str(exc))


async def _send_all(pending: list[tuple[Any, tuple]]) -> None:
    for task, args in pending:
        await asyncio.to_thread(_send, task, args)


async def drain_pending_tasks() -> None:
    """Wait for sends scheduled by commit hooks (tests, graceful shutdown)."""
    while _inflight:
        await asyncio.gather(*list(_inflight), return_exceptions=True)
