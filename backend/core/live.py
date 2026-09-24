"""Redis-backed event stream shared by every API instance."""

import asyncio
import json
from contextlib import suppress
from datetime import UTC, datetime

from fastapi import WebSocket, WebSocketDisconnect
from redis.asyncio import Redis
from sqlalchemy import event as sa_event
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from core.config import get_settings
from core.logging import get_logger

logger = get_logger("live")


def _channel(event_id: str | None) -> str:
    return f"botball:live:{event_id or 'all'}"


async def publish_live_event(event_id: str, event: str, payload: dict | None = None) -> bool:
    """Publish to the event channel and the backwards-compatible global channel."""
    message = json.dumps(
        {
            "event": event,
            "eventId": event_id,
            "payload": payload or {},
            "sentAt": datetime.now(UTC).isoformat(),
        }
    )
    redis = Redis.from_url(get_settings().redis_url, decode_responses=True)
    try:
        await redis.publish(_channel(event_id), message)
        await redis.publish(_channel(None), message)
        return True
    except Exception as exc:
        logger.warning("live_publish_failed", event_id=event_id, error=str(exc))
        return False
    finally:
        await redis.aclose()


_PENDING_KEY = "live_events_pending"
_HOOKED_KEY = "live_events_hooked"
# Strong references to in-flight publish tasks (the event loop keeps only weak
# ones), so a publish scheduled from the commit hook is never garbage-collected.
_inflight: set[asyncio.Task] = set()


def publish_after_commit(
    db: AsyncSession | Session, event_id: str | None, event: str, payload: dict | None = None
) -> None:
    """Queue a live event that is published once the session's transaction commits.

    Clients react to ``ranking_updated`` / ``schedule_updated`` by re-fetching;
    publishing before the commit let them read the old state (or, after a
    rollback, announced a change that never happened). The events are dropped
    on rollback. Identical events queued in one transaction are sent once.
    """
    if not event_id:
        return
    session = db.sync_session if isinstance(db, AsyncSession) else db
    pending: list[tuple[str, str, dict]] = session.info.setdefault(_PENDING_KEY, [])
    item = (event_id, event, payload or {})
    if item not in pending:
        pending.append(item)
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
        # A synchronous session outside an event loop (scripts): publish inline.
        asyncio.run(_publish_all(pending))
        return
    task = loop.create_task(_publish_all(pending))
    _inflight.add(task)
    task.add_done_callback(_inflight.discard)


async def _publish_all(pending: list[tuple[str, str, dict]]) -> None:
    for event_id, event, payload in pending:
        await publish_live_event(event_id, event, payload)


async def drain_pending_publishes() -> None:
    """Wait for publishes scheduled by commit hooks (tests, graceful shutdown)."""
    while _inflight:
        await asyncio.gather(*list(_inflight), return_exceptions=True)


async def stream_live_events(websocket: WebSocket, event_id: str | None) -> None:
    """Forward a Redis Pub/Sub channel to one WebSocket client."""
    await websocket.accept()
    redis = Redis.from_url(get_settings().redis_url, decode_responses=True)
    pubsub = redis.pubsub()
    receiver: asyncio.Task[str] | None = None
    try:
        await pubsub.subscribe(_channel(event_id))
        await websocket.send_json({"event": "connection", "payload": {"status": "connected"}})
        receiver = asyncio.create_task(websocket.receive_text())
        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message and message.get("type") == "message":
                await websocket.send_text(message["data"])
            if receiver.done():
                # Any client message is a keep-alive ping. A disconnect raises here.
                receiver.result()
                await websocket.send_json({"event": "pong"})
                receiver = asyncio.create_task(websocket.receive_text())
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.warning("live_stream_failed", event_id=event_id, error=str(exc))
        with suppress(Exception):
            await websocket.send_json(
                {
                    "event": "connection",
                    "payload": {"status": "disconnected", "retry": True},
                }
            )
            await websocket.close(code=1013)
    finally:
        if receiver:
            receiver.cancel()
            with suppress(asyncio.CancelledError):
                await receiver
        with suppress(Exception):
            await pubsub.unsubscribe(_channel(event_id))
            await pubsub.aclose()
            await redis.aclose()
