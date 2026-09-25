"""Authenticated live stream of one event: ``WS /api/v1/events/{event_id}/ws``.

The public stream (``/api/v1/public/events/{slug}/ws``) exists only for events
with a public view, so the signed-in pages of every other event polled every
15 s. This stream serves any event the user may read, from the same
per-process subscription (core.live.LiveHub).

Protocol
--------
1. The client opens the socket and, within ``AUTH_TIMEOUT_SECONDS``, sends
   ``{"type": "auth", "token": "<access token>"}``. The token travels in a
   message, never in the URL, so it cannot end up in proxy or access logs.
2. The server checks the token like every API request (signature, expiry,
   logout deny-list, token_version, active user), then ``events:read`` and the
   draft rule (drafts only for ``events:write``, modules.events.draft_access).
   It then streams exactly like the public socket: ``{"event": "connection",
   "payload": {"status": "connected"}}``, the event's live messages, and
   ``{"event": "pong"}`` for any other client message.
3. Whenever the client gets a new access token it sends the auth message
   again; the server re-checks it and answers ``{"event": "auth", "payload":
   {"status": "ok"}}``.
4. Every ``REVALIDATE_SECONDS`` and at the token's expiry the grant is checked
   again, each time in a short session of its own — none is held while
   streaming. The server closes the socket with

   - 4401 when the token expired (and no newer one arrived), was revoked, or
     the user was deactivated — the client refreshes its session and
     reconnects;
   - 4403 when the user may not read events (any more), 4404 when the event
     is gone or is a draft the user may not see — the client stops and falls
     back to polling;
   - 4400 when the first message is not an auth message or does not arrive
     in time;
   - 1013 when the shared subscription failed — the client reconnects.
"""

import asyncio
import json
import time
from collections.abc import Callable
from dataclasses import dataclass

from fastapi import WebSocket
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.auth import authenticate_token, has_elevated_access
from core.exceptions import UnauthorizedError
from core.live import LiveClose, stream_live_events
from modules.events.draft_access import DRAFT_READERS, is_draft_event
from modules.events.models import Event

#: How long a new socket may take to send its credentials.
AUTH_TIMEOUT_SECONDS = 10.0
#: How often a streaming socket's token and permissions are checked again
#: (revoked tokens, deactivated users, lost permissions, events turned draft).
REVALIDATE_SECONDS = 60.0

CLOSE_BAD_REQUEST = 4400
CLOSE_UNAUTHORIZED = 4401
CLOSE_FORBIDDEN = 4403
CLOSE_NOT_FOUND = 4404

READ_PERMISSION = "events:read"


def auth_token(text: str | None) -> str | None:
    """The access token of an auth message, or None for anything else."""
    if not text:
        return None
    try:
        data = json.loads(text)
    except ValueError:
        return None
    if not isinstance(data, dict) or data.get("type") != "auth":
        return None
    token = data.get("token")
    return token if isinstance(token, str) and token else None


@dataclass(frozen=True)
class Grant:
    """A checked token: who may stream this event, and until when."""

    token: str
    user_id: str
    expires_at: float


async def authorize(
    session_factory: async_sessionmaker[AsyncSession], event_id: str, token: str
) -> Grant:
    """Check `token` for streaming `event_id`; raises LiveClose when refused."""
    async with session_factory() as db:
        try:
            user, claims = await authenticate_token(token, db)
        except UnauthorizedError:
            raise LiveClose(CLOSE_UNAUTHORIZED, "unauthorized") from None
        if not await has_elevated_access(db, user, READ_PERMISSION):
            raise LiveClose(CLOSE_FORBIDDEN, "forbidden")
        exists = await db.scalar(select(Event.id).where(Event.id == event_id))
        if exists is None or (
            await is_draft_event(db, event_id)
            and not await has_elevated_access(db, user, DRAFT_READERS)
        ):
            raise LiveClose(CLOSE_NOT_FOUND, "not found")
        return Grant(token=token, user_id=str(user.id), expires_at=float(claims["exp"]))


class EventLiveGuard:
    """core.live.LiveGuard of an authenticated event stream."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        event_id: str,
        grant: Grant,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._session_factory = session_factory
        self._event_id = event_id
        self._clock = clock
        self._accept(grant)

    @property
    def grant(self) -> Grant:
        return self._grant

    def _accept(self, grant: Grant) -> None:
        self._grant = grant
        # Wall-clock time, like the token's "exp".
        self._next_check = min(grant.expires_at, self._clock() + REVALIDATE_SECONDS)

    def seconds_until_check(self) -> float:
        return self._next_check - self._clock()

    async def check(self) -> None:
        if self._clock() >= self._grant.expires_at:
            raise LiveClose(CLOSE_UNAUTHORIZED, "token expired")
        self._accept(await authorize(self._session_factory, self._event_id, self._grant.token))

    async def handle_message(self, text: str) -> dict | None:
        token = auth_token(text)
        if token is None:
            return None
        self._accept(await authorize(self._session_factory, self._event_id, token))
        return {"event": "auth", "payload": {"status": "ok"}}


async def _first_message(websocket: WebSocket) -> str | None:
    """The text of the first client message; None when the client left."""
    message = await websocket.receive()
    if message["type"] == "websocket.disconnect":
        return None
    return message.get("text") or ""


async def serve_event_stream(
    websocket: WebSocket,
    event_id: str,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Authenticate the socket, then stream the event's live channel."""
    await websocket.accept()
    try:
        text = await asyncio.wait_for(_first_message(websocket), AUTH_TIMEOUT_SECONDS)
    except TimeoutError:
        await websocket.close(code=CLOSE_BAD_REQUEST, reason="authentication timeout")
        return
    if text is None:
        return
    token = auth_token(text)
    if token is None:
        await websocket.close(code=CLOSE_BAD_REQUEST, reason="authentication required")
        return
    try:
        grant = await authorize(session_factory, event_id, token)
    except LiveClose as refused:
        await websocket.close(code=refused.code, reason=refused.reason)
        return
    await stream_live_events(
        websocket, event_id, guard=EventLiveGuard(session_factory, event_id, grant)
    )
