"""Public live stream without a pinned DB connection; cached rankings with ETags."""

import asyncio
import json
import threading
import warnings

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import AsyncAdaptedQueuePool

import core.live as live
import modules.events.routes as event_routes
from core import cache, metrics
from core.config import get_settings
from core.database import Base, get_db, get_session_factory
from main import app
from modules.events.models import EventRegistration
from modules.scoring import formula_service

with warnings.catch_warnings():
    # starlette announces a switch to httpx2; the client works unchanged.
    warnings.simplefilter("ignore")
    from starlette.testclient import TestClient

# ── WebSocket: no pool connection while streaming ─────────────────────────────


def test_public_websocket_holds_no_pool_connection_while_streaming(tmp_path, monkeypatch):
    """Two open live screens must not exhaust a one-connection pool.

    The stream used to depend on get_db, so every open WebSocket kept its pool
    connection for as long as it was open.
    """
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'ws.db'}",
        poolclass=AsyncAdaptedQueuePool,
        pool_size=1,
        max_overflow=0,
        pool_timeout=2,
    )
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def seed() -> None:
        from modules.events.models import Event
        from modules.seasons.models import Season

        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with factory() as db:
            season = Season(name="S", year=2026, is_active=True)
            db.add(season)
            await db.flush()
            db.add(
                Event(
                    season_id=season.id,
                    name="Live",
                    slug="live-ws",
                    status="live",
                    public_scoreboard=True,
                )
            )
            await db.commit()
        await engine.dispose()

    asyncio.run(seed())

    checked_out_while_streaming: list[int] = []
    release = threading.Event()

    async def fake_stream(websocket, event_id):
        await websocket.accept()
        checked_out_while_streaming.append(engine.pool.checkedout())
        await websocket.send_json({"event": "connection", "payload": {"status": "connected"}})
        while not release.is_set():
            await asyncio.sleep(0.01)

    async def request_db():
        async with factory() as session:
            yield session

    monkeypatch.setattr(event_routes, "stream_live_events", fake_stream)
    app.dependency_overrides[get_db] = request_db
    app.dependency_overrides[get_session_factory] = lambda: factory
    app.state.testing = True
    try:
        with TestClient(app) as client:
            first = client.websocket_connect("/api/v1/public/events/live-ws/ws")
            second = client.websocket_connect("/api/v1/public/events/live-ws/ws")
            with first as ws1, second as ws2:
                assert ws1.receive_json()["event"] == "connection"
                assert ws2.receive_json()["event"] == "connection"
                # Both streams are open; a normal request still gets the one
                # pooled connection.
                response = client.get("/api/v1/public/events/live-ws")
                assert response.status_code == 200
                assert engine.pool.checkedout() == 0
                release.set()
    finally:
        release.set()
        app.dependency_overrides.clear()
        app.state.testing = False
    assert checked_out_while_streaming == [0, 0]


# ── Cached rankings, ETag / 304 ───────────────────────────────────────────────


@pytest.fixture
def memory_cache(monkeypatch):
    monkeypatch.setattr(get_settings(), "cache_backend", "memory")
    cache.clear_memory()
    yield
    cache.clear_memory()


@pytest.fixture
async def live_event(db, event, team):
    event.status = "live"
    event.public_results = True
    db.add(EventRegistration(event_id=event.id, team_id=team.id))
    await db.commit()
    return event


async def _score(client, auth_headers, event, team, value, key):
    response = await client.post(
        f"/api/v1/events/{event.id}/matches",
        headers=auth_headers,
        json={
            "team_id": team.id,
            "raw_scores": {"points": value},
            "idempotency_key": f"perf-key-{key}",
        },
    )
    assert response.status_code == 201, response.text


@pytest.fixture
def no_publish(monkeypatch):
    async def fake_publish(event_id, event, payload=None):
        return True

    monkeypatch.setattr(live, "publish_live_event", fake_publish)


@pytest.mark.asyncio
@pytest.mark.usefixtures("memory_cache", "no_publish")
async def test_public_ranking_answers_304_until_a_score_is_committed(
    client, db, auth_headers, live_event, team
):
    url = f"/api/v1/public/events/{live_event.slug}/ranking"
    await _score(client, auth_headers, live_event, team, 10, "cache-1")
    await db.commit()
    await live.drain_pending_publishes()

    first = await client.get(url)
    assert first.status_code == 200
    etag = first.headers["etag"]
    assert first.headers["cache-control"] == "public, no-cache"
    assert first.json()[0]["seed_score"] == 10

    again = await client.get(url, headers={"If-None-Match": etag})
    assert again.status_code == 304 and again.content == b""
    assert again.headers["etag"] == etag

    # A committed score publishes ranking_updated, which bumps the version.
    await _score(client, auth_headers, live_event, team, 30, "cache-2")
    await db.commit()
    await live.drain_pending_publishes()
    fresh = await client.get(url, headers={"If-None-Match": etag})
    assert fresh.status_code == 200
    assert fresh.headers["etag"] != etag
    assert fresh.json()[0]["seed_score"] == 20  # average of the best two: (10 + 30) / 2


@pytest.mark.asyncio
@pytest.mark.usefixtures("memory_cache", "no_publish")
async def test_overall_ranking_is_computed_once_per_version(
    client, db, auth_headers, live_event, team, monkeypatch
):
    await _score(client, auth_headers, live_event, team, 10, "overall-1")
    await db.commit()
    await live.drain_pending_publishes()
    calls: list[str] = []
    original = formula_service.compute_overall_ranking

    async def counting(*args, **kwargs):
        calls.append("x")
        return await original(*args, **kwargs)

    monkeypatch.setattr(formula_service, "compute_overall_ranking", counting)
    url = f"/api/scoring/events/{live_event.id}/ranking/overall"
    bodies = [(await client.get(url, headers=auth_headers)).json() for _ in range(3)]
    assert len(calls) == 1
    assert bodies[0] == bodies[1] == bodies[2]
    assert (await client.get(url, headers=auth_headers)).headers["cache-control"] == (
        "private, no-cache"
    )

    # A formula change announces nothing live but still invalidates.
    response = await client.post(
        f"/api/scoring/formulas/seasons/{live_event.season_id}/botball/reset",
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    await db.commit()
    await live.drain_pending_publishes()
    await client.get(url, headers=auth_headers)
    assert len(calls) == 2


@pytest.mark.asyncio
@pytest.mark.usefixtures("no_publish")
async def test_cached_and_uncached_bodies_are_identical(
    client, db, auth_headers, live_event, team, monkeypatch
):
    await _score(client, auth_headers, live_event, team, 12, "same-body")
    await db.commit()
    urls = [
        f"/api/v1/public/events/{live_event.slug}/ranking",
        f"/api/v1/public/events/{live_event.slug}/results",
        f"/api/scoring/events/{live_event.id}/ranking/extended",
        f"/api/scoring/events/{live_event.id}/ranking/overall",
    ]
    uncached = [(await client.get(u, headers=auth_headers)) for u in urls]
    monkeypatch.setattr(get_settings(), "cache_backend", "memory")
    cache.clear_memory()
    for response, url in zip(uncached, urls, strict=True):
        miss = await client.get(url, headers=auth_headers)
        hit = await client.get(url, headers=auth_headers)
        assert json.loads(miss.content) == json.loads(response.content) == json.loads(hit.content)
        assert miss.headers["etag"] == hit.headers["etag"] == response.headers["etag"]
    cache.clear_memory()


@pytest.mark.asyncio
@pytest.mark.usefixtures("no_publish")
async def test_redis_outage_falls_back_to_computing(
    client, db, auth_headers, live_event, team, monkeypatch
):
    await _score(client, auth_headers, live_event, team, 8, "outage-1")
    await db.commit()
    await live.drain_pending_publishes()
    calls: list[str] = []

    class Broken:
        async def get(self, *args, **kwargs):
            calls.append("get")
            raise ConnectionError("down")

        async def set(self, *args, **kwargs):
            raise ConnectionError("down")

    monkeypatch.setattr(get_settings(), "cache_backend", "redis")
    monkeypatch.setattr(cache, "_client", lambda: Broken())
    cache.clear_memory()
    before = metrics.REDIS_FAIL_OPEN["cache"]

    url = f"/api/v1/public/events/{live_event.slug}/ranking"
    first = await client.get(url)
    second = await client.get(url, headers={"If-None-Match": first.headers["etag"]})
    assert first.status_code == 200 and first.json()[0]["seed_score"] == 8
    # ETags work without a cache as well.
    assert second.status_code == 304
    # After the first failure Redis is left alone for a few seconds.
    assert calls == ["get"]
    assert metrics.REDIS_FAIL_OPEN["cache"] == before + 1
    cache.clear_memory()


@pytest.mark.asyncio
async def test_version_bump_runs_after_commit_only(db, event, memory_cache):
    event_id = event.id
    live.invalidate_after_commit(db, event_id)
    await db.flush()
    await live.drain_pending_publishes()
    assert await cache.current_version(event_id) == 0
    await db.rollback()
    await db.commit()
    await live.drain_pending_publishes()
    assert await cache.current_version(event_id) == 0
    live.invalidate_after_commit(db, event_id)
    await db.commit()
    await live.drain_pending_publishes()
    assert await cache.current_version(event_id) == 1


def test_etag_matching_accepts_lists_and_weak_tags():
    tag = cache.Payload.of(b"[]").etag
    assert cache._etag_matches(f'"other", W/{tag}', tag)
    assert cache._etag_matches("*", tag)
    assert not cache._etag_matches('"other"', tag)
    assert not cache._etag_matches(None, tag)
