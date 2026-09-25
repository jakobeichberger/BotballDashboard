"""Authenticated live stream of an event (modules.events.live_socket)."""

import asyncio
import json
import warnings
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi import WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import AsyncAdaptedQueuePool
from starlette.websockets import WebSocketState

import core.live as live
from core import token_denylist
from core.auth import ALGORITHM, create_refresh_token, decode_token
from core.config import get_settings
from core.database import Base, get_db, get_session_factory
from main import app
from modules.events import live_socket
from modules.events.live_socket import (
    CLOSE_BAD_REQUEST,
    CLOSE_FORBIDDEN,
    CLOSE_NOT_FOUND,
    CLOSE_UNAUTHORIZED,
    EventLiveGuard,
    Grant,
)
from modules.events.models import Event
from tests.integration.test_security_regressions_3 import GUEST, _user
from tests.integration.test_worker_and_infrastructure import (  # noqa: F401 - fixture
    _FakePubSub,
    _pmessage,
    fake_hub,
)

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    from starlette.testclient import TestClient

ORGANIZER = ["events:read", "events:write", "scoring:read"]


class _Socket:
    """A WebSocket stand-in: queued client messages, recorded frames and close."""

    def __init__(self) -> None:
        self.application_state = WebSocketState.CONNECTING
        self.incoming: asyncio.Queue = asyncio.Queue()
        self.sent: list = []
        self.closed: tuple[int, str] | None = None
        self.frame = asyncio.Event()

    async def accept(self) -> None:
        self.application_state = WebSocketState.CONNECTED

    async def _next(self):
        item = await self.incoming.get()
        if isinstance(item, Exception):
            raise item
        return item

    async def receive(self) -> dict:
        item = await self._next()
        return {"type": "websocket.receive", "text": item}

    async def receive_text(self) -> str:
        return await self._next()

    async def send_json(self, data) -> None:
        self.sent.append(data)
        self.frame.set()

    async def send_text(self, data: str) -> None:
        self.sent.append(json.loads(data))
        self.frame.set()

    async def close(self, code: int = 1000, reason: str = "") -> None:
        self.closed = (code, reason)
        self.frame.set()

    def say(self, message) -> None:
        self.incoming.put_nowait(message if isinstance(message, str) else json.dumps(message))

    async def wait_for(self, predicate, timeout: float = 1.0) -> None:
        async def poll() -> None:
            while not predicate():
                self.frame.clear()
                await self.frame.wait()

        await asyncio.wait_for(poll(), timeout)


class _SessionContext:
    def __init__(self, db) -> None:
        self.db = db

    async def __aenter__(self):
        return self.db

    async def __aexit__(self, *exc):
        return False


@pytest.fixture
def sessions(db):
    """The session factory of the stream, bound to the test's transaction."""
    return lambda: _SessionContext(db)


def _auth(headers: dict) -> dict:
    return {"type": "auth", "token": headers["Authorization"].split(" ", 1)[1]}


async def _serve(socket: _Socket, event_id: str, sessions) -> asyncio.Task:
    return asyncio.create_task(live_socket.serve_event_stream(socket, event_id, sessions))


def _subscribed() -> bool:
    return bool(_FakePubSub.instances) and live.live_hub().subscriber_count > 0


# ── Handshake ─────────────────────────────────────────────────────────────────


def test_auth_message_parsing():
    assert live_socket.auth_token('{"type": "auth", "token": "abc"}') == "abc"
    for text in (None, "", "ping", "[]", '{"type": "auth"}', '{"type": "x", "token": "a"}'):
        assert live_socket.auth_token(text) is None
    assert live_socket.auth_token('{"type": "auth", "token": 5}') is None


@pytest.mark.asyncio
@pytest.mark.usefixtures("fake_hub")
async def test_streams_after_authenticating_with_the_first_message(db, event, sessions):
    _, headers = await _user(db, "live-guest@test.com", GUEST)
    socket = _Socket()
    stream = await _serve(socket, event.id, sessions)
    socket.say(_auth(headers))
    await socket.wait_for(lambda: socket.sent)
    assert socket.sent[0] == {"event": "connection", "payload": {"status": "connected"}}
    await socket.wait_for(_subscribed)

    # The event's messages arrive; other events' do not.
    await _FakePubSub.instances[0].messages.put(_pmessage("elsewhere", '{"event": "x"}'))
    await _FakePubSub.instances[0].messages.put(_pmessage(event.id, '{"event": "ranking_updated"}'))
    await socket.wait_for(lambda: len(socket.sent) >= 2)
    assert socket.sent[1] == {"event": "ranking_updated"}

    socket.say("ping")
    await socket.wait_for(lambda: len(socket.sent) >= 3)
    assert socket.sent[2] == {"event": "pong"}

    # A refreshed token is sent in-band and checked again.
    _, fresh = await _user(db, "live-guest-2@test.com", GUEST)
    socket.say(_auth(fresh))
    await socket.wait_for(lambda: len(socket.sent) >= 4)
    assert socket.sent[3] == {"event": "auth", "payload": {"status": "ok"}}

    socket.incoming.put_nowait(WebSocketDisconnect())
    await asyncio.wait_for(stream, 1)
    assert live.live_hub().subscriber_count == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("first", ["ping", '{"type": "auth"}', "not json"])
async def test_a_first_message_without_credentials_is_refused(db, event, sessions, first):
    socket = _Socket()
    stream = await _serve(socket, event.id, sessions)
    socket.say(first)
    await asyncio.wait_for(stream, 1)
    assert socket.closed == (CLOSE_BAD_REQUEST, "authentication required")
    assert socket.sent == []


@pytest.mark.asyncio
async def test_a_silent_client_is_closed_after_the_auth_timeout(db, event, sessions, monkeypatch):
    monkeypatch.setattr(live_socket, "AUTH_TIMEOUT_SECONDS", 0.05)
    socket = _Socket()
    await asyncio.wait_for(await _serve(socket, event.id, sessions), 1)
    assert socket.closed == (CLOSE_BAD_REQUEST, "authentication timeout")


@pytest.mark.asyncio
async def test_a_client_leaving_before_authenticating_is_no_error(db, event, sessions):
    socket = _Socket()

    async def left() -> dict:
        return {"type": "websocket.disconnect", "code": 1001}

    socket.receive = left  # type: ignore[method-assign]
    await asyncio.wait_for(await _serve(socket, event.id, sessions), 1)
    assert socket.closed is None and socket.sent == []


# ── Who may stream ────────────────────────────────────────────────────────────


async def _refused(event_id: str, sessions, token: str) -> tuple[int, str] | None:
    socket = _Socket()
    stream = await _serve(socket, event_id, sessions)
    socket.say({"type": "auth", "token": token})
    await asyncio.wait_for(stream, 1)
    return socket.closed


@pytest.mark.asyncio
async def test_invalid_expired_and_revoked_tokens_are_refused(db, event, sessions):
    user, headers = await _user(db, "live-revoked@test.com", GUEST)
    token = headers["Authorization"].split(" ", 1)[1]
    assert await _refused(event.id, sessions, "garbage") == (CLOSE_UNAUTHORIZED, "unauthorized")

    expired = jwt.encode(
        {
            "sub": user.id,
            "exp": datetime.now(UTC) - timedelta(seconds=5),
            "type": "access",
            "jti": "old",
        },
        get_settings().jwt_secret_key,
        algorithm=ALGORITHM,
    )
    assert (await _refused(event.id, sessions, expired))[0] == CLOSE_UNAUTHORIZED

    # A refresh token is not an access token.
    refresh = create_refresh_token(user.id)
    assert (await _refused(event.id, sessions, refresh))[0] == CLOSE_UNAUTHORIZED

    # Logged out: the token's jti is on the deny-list.
    claims = decode_token(token)
    await token_denylist.deny(claims["jti"], claims["exp"])
    assert (await _refused(event.id, sessions, token))[0] == CLOSE_UNAUTHORIZED


@pytest.mark.asyncio
async def test_users_without_events_read_are_refused(db, event, sessions):
    _, headers = await _user(db, "live-noread@test.com", ["scoring:read"])
    token = headers["Authorization"].split(" ", 1)[1]
    assert await _refused(event.id, sessions, token) == (CLOSE_FORBIDDEN, "forbidden")


@pytest.mark.asyncio
@pytest.mark.usefixtures("fake_hub")
async def test_draft_events_stream_only_for_organizers(db, season, sessions):
    draft = Event(season_id=season.id, name="Draft Cup", slug="draft-cup", status="draft")
    db.add(draft)
    await db.commit()
    _, guest = await _user(db, "live-draft-guest@test.com", GUEST)
    _, organizer = await _user(db, "live-draft-org@test.com", ORGANIZER)

    guest_token = guest["Authorization"].split(" ", 1)[1]
    assert await _refused(draft.id, sessions, guest_token) == (CLOSE_NOT_FOUND, "not found")
    assert (await _refused("no-such-event", sessions, guest_token))[0] == CLOSE_NOT_FOUND

    socket = _Socket()
    stream = await _serve(socket, draft.id, sessions)
    socket.say(_auth(organizer))
    await socket.wait_for(lambda: socket.sent)
    assert socket.sent[0]["event"] == "connection"
    socket.incoming.put_nowait(WebSocketDisconnect())
    await asyncio.wait_for(stream, 1)


# ── While streaming ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.usefixtures("fake_hub")
async def test_revocation_closes_a_running_stream(db, event, sessions, monkeypatch):
    monkeypatch.setattr(live_socket, "REVALIDATE_SECONDS", 0.05)
    user, headers = await _user(db, "live-running@test.com", GUEST)
    socket = _Socket()
    stream = await _serve(socket, event.id, sessions)
    socket.say(_auth(headers))
    await socket.wait_for(lambda: socket.sent)

    # A password change (or deactivation) bumps the token version.
    user.token_version = (user.token_version or 0) + 1
    await db.commit()
    await asyncio.wait_for(stream, 1)
    assert socket.closed == (CLOSE_UNAUTHORIZED, "unauthorized")
    assert live.live_hub().subscriber_count == 0


@pytest.mark.asyncio
@pytest.mark.usefixtures("fake_hub")
async def test_an_event_turned_draft_closes_the_stream_of_a_guest(db, event, sessions, monkeypatch):
    monkeypatch.setattr(live_socket, "REVALIDATE_SECONDS", 0.05)
    _, headers = await _user(db, "live-hidden@test.com", GUEST)
    socket = _Socket()
    stream = await _serve(socket, event.id, sessions)
    socket.say(_auth(headers))
    await socket.wait_for(lambda: socket.sent)
    event.status = "draft"
    await db.commit()
    await asyncio.wait_for(stream, 1)
    assert socket.closed == (CLOSE_NOT_FOUND, "not found")


@pytest.mark.asyncio
@pytest.mark.usefixtures("fake_hub")
async def test_a_rejected_new_token_closes_the_stream(db, event, sessions):
    _, headers = await _user(db, "live-reauth@test.com", GUEST)
    socket = _Socket()
    stream = await _serve(socket, event.id, sessions)
    socket.say(_auth(headers))
    await socket.wait_for(lambda: socket.sent)
    socket.say({"type": "auth", "token": "forged"})
    await asyncio.wait_for(stream, 1)
    assert socket.closed == (CLOSE_UNAUTHORIZED, "unauthorized")


class _Clock:
    def __init__(self, now: float) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


@pytest.mark.asyncio
async def test_guard_checks_at_expiry_and_revalidates_in_between(db, event, sessions):
    _, headers = await _user(db, "live-clock@test.com", GUEST)
    token = headers["Authorization"].split(" ", 1)[1]
    clock = _Clock(1_000.0)
    guard = EventLiveGuard(sessions, event.id, Grant(token, "u", expires_at=1_030.0), clock)
    # The token expires before the next periodic check: check at expiry.
    assert guard.seconds_until_check() == 30.0
    clock.now = 1_030.0
    with pytest.raises(live.LiveClose) as closed:
        await guard.check()
    assert closed.value.code == CLOSE_UNAUTHORIZED

    # A long-lived grant is re-checked every REVALIDATE_SECONDS; a successful
    # check takes the expiry from the (real) token again.
    guard = EventLiveGuard(sessions, event.id, Grant(token, "u", expires_at=10_000.0), clock)
    assert guard.seconds_until_check() == live_socket.REVALIDATE_SECONDS
    clock.now += live_socket.REVALIDATE_SECONDS
    await guard.check()
    assert guard.grant.expires_at == decode_token(token)["exp"]

    # A new token replaces the grant.
    _, fresh = await _user(db, "live-clock-2@test.com", GUEST)
    reply = await guard.handle_message(json.dumps(_auth(fresh)))
    assert reply == {"event": "auth", "payload": {"status": "ok"}}
    assert guard.grant.token == _auth(fresh)["token"]
    assert await guard.handle_message("ping") is None


# ── Through the real route ────────────────────────────────────────────────────


def test_route_authenticates_and_holds_no_pool_connection(tmp_path, monkeypatch):
    """Two open sockets and a request share a one-connection pool."""
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'live.db'}",
        poolclass=AsyncAdaptedQueuePool,
        pool_size=1,
        max_overflow=0,
        pool_timeout=2,
    )
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    ids: dict[str, str] = {}

    async def seed() -> None:
        from modules.seasons.models import Season

        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with factory() as db:
            season = Season(name="S", year=2026, is_active=True)
            db.add(season)
            await db.flush()
            internal = Event(season_id=season.id, name="Internal", slug="internal", status="live")
            db.add(internal)
            await db.flush()
            ids["event"] = internal.id
            user, headers = await _user(db, "live-route@test.com", GUEST)
            ids["token"] = headers["Authorization"].split(" ", 1)[1]
        await engine.dispose()

    asyncio.run(seed())

    class _Redis:
        def pubsub(self):
            return _FakePubSub()

        async def aclose(self) -> None:
            pass

    async def request_db():
        async with factory() as session:
            yield session

    monkeypatch.setattr(live.LiveHub, "_client", lambda self: _Redis())
    monkeypatch.setattr(live, "_hub", None)
    app.dependency_overrides[get_db] = request_db
    app.dependency_overrides[get_session_factory] = lambda: factory
    app.state.testing = True
    url = f"/api/v1/events/{ids['event']}/ws"
    headers = {"Authorization": f"Bearer {ids['token']}"}
    try:
        with TestClient(app) as client:
            with client.websocket_connect(url) as first, client.websocket_connect(url) as second:
                for socket in (first, second):
                    socket.send_json({"type": "auth", "token": ids["token"]})
                    assert socket.receive_json()["payload"] == {"status": "connected"}
                assert engine.pool.checkedout() == 0
                response = client.get(f"/api/v1/events/{ids['event']}", headers=headers)
                assert response.status_code == 200
                first.send_text("ping")
                assert first.receive_json() == {"event": "pong"}

            with client.websocket_connect(url) as refused:
                refused.send_json({"type": "auth", "token": "nope"})
                with pytest.raises(WebSocketDisconnect) as closed:
                    refused.receive_json()
                assert closed.value.code == CLOSE_UNAUTHORIZED
    finally:
        app.dependency_overrides.clear()
        app.state.testing = False
        live._hub = None
