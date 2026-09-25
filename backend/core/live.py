"""Redis-backed event stream shared by every API instance.

Publishing uses one shared Redis client per process (core.redis_client).
Receiving uses one Pub/Sub subscription per process — a pattern subscription
on every live channel — that fans each message out to the WebSockets of this
process watching that channel (``LiveHub``). Previously every WebSocket opened
its own Redis connection and subscription, so a hall full of scoreboards and
phones meant as many Redis connections.
"""

import asyncio
import json
from collections import defaultdict
from contextlib import suppress
from datetime import UTC, datetime
from typing import Protocol

from fastapi import WebSocket, WebSocketDisconnect
from redis.asyncio import Redis
from sqlalchemy import event as sa_event
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from starlette.websockets import WebSocketState

from core.config import get_settings
from core.logging import get_logger
from core.redis_client import REDIS_ERRORS, shared_redis

logger = get_logger("live")

_CHANNEL_PREFIX = "botball:live:"

#: Live events after which cached rankings/results/schedules of the event are
#: stale (see core.cache). Their version is bumped before the event goes out,
#: so clients re-fetching on it get fresh data.
CACHE_INVALIDATING_EVENTS = frozenset({"ranking_updated", "schedule_updated"})


def _channel(event_id: str | None) -> str:
    return f"{_CHANNEL_PREFIX}{event_id or 'all'}"


def _publisher() -> Redis:
    return shared_redis("live", timeout=1.0, connect_timeout=1.0)


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
    try:
        async with _publisher().pipeline(transaction=False) as pipe:
            pipe.publish(_channel(event_id), message)
            pipe.publish(_channel(None), message)
            await pipe.execute()
        return True
    except REDIS_ERRORS as exc:
        logger.warning("live_publish_failed", event_id=event_id, error=str(exc))
        return False


_PENDING_KEY = "live_events_pending"
_HOOKED_KEY = "live_events_hooked"
# Strong references to in-flight publish tasks (the event loop keeps only weak
# ones), so a publish scheduled from the commit hook is never garbage-collected.
_inflight: set[asyncio.Task] = set()


def _queue_after_commit(db: AsyncSession | Session, item: tuple[str, str | None, dict]) -> None:
    session = db.sync_session if isinstance(db, AsyncSession) else db
    pending: list[tuple[str, str | None, dict]] = session.info.setdefault(_PENDING_KEY, [])
    if item not in pending:
        pending.append(item)
    if not session.info.get(_HOOKED_KEY):
        sa_event.listen(session, "after_commit", _after_commit)
        sa_event.listen(session, "after_rollback", _after_rollback)
        session.info[_HOOKED_KEY] = True


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
    _queue_after_commit(db, (event_id, event, payload or {}))


def invalidate_after_commit(db: AsyncSession | Session, event_id: str | None) -> None:
    """Drop the event's cached rankings/results once the transaction commits.

    For changes that affect them without a live event of their own (formula
    sets, registrations); nothing is published.
    """
    if not event_id:
        return
    _queue_after_commit(db, (event_id, None, {}))


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


async def _publish_all(pending: list[tuple[str, str | None, dict]]) -> None:
    from core import cache

    bumped: set[str] = set()
    for event_id, event, payload in pending:
        if (event is None or event in CACHE_INVALIDATING_EVENTS) and event_id not in bumped:
            await cache.bump_version(event_id)
            bumped.add(event_id)
        if event is not None:
            await publish_live_event(event_id, event, payload)


async def drain_pending_publishes() -> None:
    """Wait for publishes scheduled by commit hooks (tests, graceful shutdown)."""
    while _inflight:
        await asyncio.gather(*list(_inflight), return_exceptions=True)


# ── Receiving: one subscription per process ───────────────────────────────────

#: Messages a slow client may fall behind by; older ones are dropped (clients
#: only use them as "re-fetch now" hints).
_QUEUE_SIZE = 100
#: How long a new WebSocket waits for the shared subscription to come up.
_SUBSCRIBE_TIMEOUT = 5.0
#: Queued in place of a message when the shared subscription broke.
_LOST = None


class _Reader:
    """One run of the shared subscription (restarted after an error)."""

    def __init__(self) -> None:
        self.ready = asyncio.Event()
        self.error: Exception | None = None
        self.task: asyncio.Task | None = None


class LiveHub:
    """Fans one Redis pattern subscription out to local WebSocket queues.

    The reader task starts with the first subscriber and stops with the last
    one. If Redis fails, every subscriber receives ``_LOST`` (its WebSocket
    closes with 1013 so the client reconnects) and the next subscriber starts
    a fresh reader.
    """

    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop
        self.queues: dict[str, set[asyncio.Queue[str | None]]] = defaultdict(set)
        self._reader: _Reader | None = None

    def _client(self) -> Redis:
        # Reads block for up to a second per poll, so no short socket timeout.
        return Redis.from_url(
            get_settings().redis_url, decode_responses=True, socket_connect_timeout=2.0
        )

    @property
    def subscriber_count(self) -> int:
        return sum(len(queues) for queues in self.queues.values())

    async def subscribe(self, channel: str) -> asyncio.Queue[str | None]:
        queue: asyncio.Queue[str | None] = asyncio.Queue(maxsize=_QUEUE_SIZE)
        self.queues[channel].add(queue)
        reader = self._reader
        if reader is None or (reader.task is not None and reader.task.done()):
            reader = self._reader = _Reader()
            reader.task = self.loop.create_task(self._run(reader))
        try:
            await asyncio.wait_for(reader.ready.wait(), _SUBSCRIBE_TIMEOUT)
        except Exception:
            self.unsubscribe(channel, queue)
            raise
        if reader.error is not None:
            self.unsubscribe(channel, queue)
            raise reader.error
        return queue

    def unsubscribe(self, channel: str, queue: asyncio.Queue[str | None]) -> None:
        queues = self.queues.get(channel)
        if queues is not None:
            queues.discard(queue)
            if not queues:
                del self.queues[channel]
        if not self.queues and self._reader is not None:
            if self._reader.task is not None:
                self._reader.task.cancel()
            self._reader = None

    def _dispatch(self, channel: str, data: str | None) -> None:
        for queue in list(self.queues.get(channel, ())):
            if queue.full():
                with suppress(asyncio.QueueEmpty):
                    queue.get_nowait()
            queue.put_nowait(data)

    async def _run(self, reader: _Reader) -> None:
        client = self._client()
        pubsub = client.pubsub()
        try:
            await pubsub.psubscribe(f"{_CHANNEL_PREFIX}*")
            reader.ready.set()
            while True:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if message and message.get("type") == "pmessage":
                    self._dispatch(message["channel"], message["data"])
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - whatever ends the shared subscription, every subscriber must hear of it
            logger.warning("live_subscription_failed", error=str(exc))
            reader.error = exc
            reader.ready.set()
            if self._reader is reader:
                self._reader = None
            for channel in list(self.queues):
                self._dispatch(channel, _LOST)
        finally:
            with suppress(Exception):
                await pubsub.aclose()
                await client.aclose()


_hub: LiveHub | None = None


def live_hub() -> LiveHub:
    """The hub of the running event loop (one per process in production)."""
    global _hub
    loop = asyncio.get_running_loop()
    if _hub is None or _hub.loop is not loop:
        _hub = LiveHub(loop)
    return _hub


class LiveClose(Exception):
    """Raised by a LiveGuard to end a stream with a WebSocket close code."""

    def __init__(self, code: int, reason: str = "") -> None:
        super().__init__(reason or str(code))
        self.code = code
        self.reason = reason


class LiveGuard(Protocol):
    """Access control of an authenticated stream (see modules.events.live_socket).

    ``stream_live_events`` calls ``check`` whenever ``seconds_until_check``
    has passed, and hands every client message to ``handle_message`` first.
    Both may raise LiveClose to end the stream.
    """

    def seconds_until_check(self) -> float: ...

    async def check(self) -> None: ...

    async def handle_message(self, text: str) -> dict | None:
        """The reply to a message it handled, or None for a keep-alive ping."""
        ...


async def stream_live_events(
    websocket: WebSocket, event_id: str | None, guard: LiveGuard | None = None
) -> None:
    """Forward an event's live channel to one WebSocket client.

    Accepts the socket unless the caller already did (an authenticated stream
    accepts it to receive the credentials first). No database session is held
    while streaming; a guard opens short ones of its own when it re-checks.
    """
    if websocket.application_state == WebSocketState.CONNECTING:
        await websocket.accept()
    hub = live_hub()
    channel = _channel(event_id)
    queue: asyncio.Queue[str | None] | None = None
    receiver: asyncio.Future[str] | None = None
    getter: asyncio.Future[str | None] | None = None
    try:
        queue = await hub.subscribe(channel)
        await websocket.send_json({"event": "connection", "payload": {"status": "connected"}})
        receiver = asyncio.ensure_future(websocket.receive_text())
        getter = asyncio.ensure_future(queue.get())
        while True:
            timeout = max(0.0, guard.seconds_until_check()) if guard else None
            done, _ = await asyncio.wait(
                {receiver, getter}, timeout=timeout, return_when=asyncio.FIRST_COMPLETED
            )
            if guard and not done:
                await guard.check()
                continue
            if getter in done:
                data = getter.result()
                if data is _LOST:
                    raise ConnectionError("live subscription lost")
                await websocket.send_text(data)
                getter = asyncio.ensure_future(queue.get())
            if receiver in done:
                # A disconnect raises here. Anything the guard does not handle
                # (credentials) is a keep-alive ping.
                text = receiver.result()
                reply = await guard.handle_message(text) if guard else None
                await websocket.send_json(reply or {"event": "pong"})
                receiver = asyncio.ensure_future(websocket.receive_text())
    except WebSocketDisconnect:
        pass
    except LiveClose as close:
        with suppress(Exception):
            await websocket.close(code=close.code, reason=close.reason)
    except Exception as exc:  # noqa: BLE001 - the client is told to reconnect, whatever broke
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
        for future in (receiver, getter):
            if future is not None:
                future.cancel()
                with suppress(asyncio.CancelledError, Exception):
                    await future
        if queue is not None:
            hub.unsubscribe(channel, queue)
