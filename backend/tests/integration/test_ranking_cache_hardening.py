"""Ranking cache: no entries for made-up categories, one computation per miss.

* ``category`` is checked against the season's categories before anything
  is cached: an anonymous client could otherwise store one Redis entry of up
  to ~60 KB per request (review 2, security #4).
* Concurrent misses of one key compute once (single flight in the process,
  a short Redis lock across instances): after every committed score all
  open scoreboards used to recompute the ranking at the same moment
  (review 2, performance #2).
"""

import asyncio
import time

import pytest

from core import cache
from core.config import get_settings
from modules.scoring.models import Ranking


@pytest.fixture
def memory_cache(monkeypatch):
    monkeypatch.setattr(get_settings(), "cache_backend", "memory")
    cache.clear_memory()
    yield
    cache.clear_memory()


# ── category validation ───────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.usefixtures("memory_cache")
@pytest.mark.parametrize("kind", ["extended", "overall"])
async def test_unknown_category_is_refused_before_caching(client, event, kind):
    url = f"/api/scoring/events/{event.id}/ranking/{kind}"
    for category in ["nosuchcategory", "x" + "a" * 8000, "Botball"]:
        resp = await client.get(url, params={"category": category})
        assert resp.status_code == 422, (category, resp.status_code)
    assert cache._memory == {}


@pytest.mark.asyncio
@pytest.mark.usefixtures("memory_cache")
@pytest.mark.parametrize("kind", ["extended", "overall"])
async def test_season_categories_still_work(client, event, kind):
    url = f"/api/scoring/events/{event.id}/ranking/{kind}"
    for params in ({}, {"category": "botball"}):
        resp = await client.get(url, params=params)
        assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
@pytest.mark.usefixtures("memory_cache")
async def test_historical_category_with_rankings_is_accepted(client, db, event, team):
    # A key no longer in the registry, but still carried by stored rankings.
    db.add(
        Ranking(
            season_id=event.season_id,
            event_id=event.id,
            team_id=team.id,
            category="legacy_cat",
            rank=1,
        )
    )
    await db.commit()
    url = f"/api/scoring/events/{event.id}/ranking/extended"
    resp = await client.get(url, params={"category": "legacy_cat"})
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
@pytest.mark.usefixtures("memory_cache")
async def test_season_ranking_route_validates_too(client, season, event):
    url = f"/api/scoring/seasons/{season.id}/ranking/extended"
    resp = await client.get(url, params={"category": "nosuchcategory", "event_id": event.id})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_public_results_offset_is_bounded(client, event):
    resp = await client.get(
        f"/api/v1/public/events/{event.slug}/results", params={"offset": 10_000_000}
    )
    assert resp.status_code == 422


# ── single flight ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.usefixtures("memory_cache")
async def test_concurrent_misses_compute_once():
    calls = 0

    async def compute() -> bytes:
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.05)
        return b'{"n": 1}'

    payloads = await asyncio.gather(
        *(cache.cached_payload("t", "ev-1", "p", compute) for _ in range(50))
    )
    assert calls == 1
    assert len({p.etag for p in payloads}) == 1


@pytest.mark.asyncio
@pytest.mark.usefixtures("memory_cache")
async def test_followers_compute_themselves_when_the_leader_fails():
    calls = 0

    async def compute() -> bytes:
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.02)
        if calls == 1:
            raise RuntimeError("leader broke")
        return b"[]"

    results = await asyncio.gather(
        *(cache.cached_payload("t", "ev-2", "p", compute) for _ in range(3)),
        return_exceptions=True,
    )
    assert isinstance(results[0], RuntimeError)
    assert all(isinstance(r, cache.Payload) for r in results[1:])
    assert cache._flights == {}


@pytest.mark.asyncio
@pytest.mark.usefixtures("memory_cache")
async def test_followers_survive_a_cancelled_leader():
    started = asyncio.Event()

    async def slow() -> bytes:
        started.set()
        await asyncio.sleep(10)
        return b"[]"

    async def fast() -> bytes:
        return b"[1]"

    leader = asyncio.create_task(cache.cached_payload("t", "ev-3", "p", slow))
    await started.wait()
    follower = asyncio.create_task(cache.cached_payload("t", "ev-3", "p", fast))
    await asyncio.sleep(0.01)
    leader.cancel()
    assert (await follower).body == b"[1]"


class _FakeRedis:
    """Enough of redis.asyncio.Redis for the cache: GET, SET NX PX, EVAL, INCR."""

    def __init__(self) -> None:
        self.data: dict[str, bytes] = {}

    async def get(self, key):
        return self.data.get(key)

    async def set(self, key, value, ex=None, nx=False, px=None):
        if nx and key in self.data:
            return None
        self.data[key] = value if isinstance(value, bytes) else str(value).encode()
        return True

    async def eval(self, script, numkeys, key, token):
        if self.data.get(key) == token.encode():
            del self.data[key]
            return 1
        return 0


@pytest.fixture
def fake_redis(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(get_settings(), "cache_backend", "redis")
    monkeypatch.setattr(cache, "_client", lambda: fake)
    cache.clear_memory()
    yield fake
    cache.clear_memory()


@pytest.mark.asyncio
async def test_other_instance_waits_for_the_lock_holders_entry(fake_redis):
    key = cache._entry_key("t", "ev-4", 0, "p")
    fake_redis.data[f"{key}:lock"] = b"held-by-another-instance"
    calls = 0

    async def compute() -> bytes:
        nonlocal calls
        calls += 1
        return b"mine"

    async def other_instance_finishes():
        await asyncio.sleep(0.12)
        fake_redis.data[key] = cache.Payload.of(b"theirs").encode()
        del fake_redis.data[f"{key}:lock"]

    payload, _ = await asyncio.gather(
        cache.cached_payload("t", "ev-4", "p", compute), other_instance_finishes()
    )
    assert payload.body == b"theirs" and calls == 0


@pytest.mark.asyncio
async def test_lock_holder_that_never_delivers_does_not_block_for_long(fake_redis, monkeypatch):
    monkeypatch.setattr(cache, "_LOCK_TTL_MS", 200)
    key = cache._entry_key("t", "ev-5", 0, "p")
    fake_redis.data[f"{key}:lock"] = b"stuck"

    async def compute() -> bytes:
        return b"mine"

    started = time.perf_counter()
    payload = await cache.cached_payload("t", "ev-5", "p", compute)
    assert payload.body == b"mine"
    assert time.perf_counter() - started < 1.0
    # The foreign lock is left alone; our entry is stored.
    assert fake_redis.data[f"{key}:lock"] == b"stuck"
    assert fake_redis.data[key] == payload.encode()


@pytest.mark.asyncio
async def test_lock_is_taken_and_released_by_the_computing_instance(fake_redis):
    key = cache._entry_key("t", "ev-6", 0, "p")
    seen_locks: list[bytes | None] = []

    async def compute() -> bytes:
        seen_locks.append(fake_redis.data.get(f"{key}:lock"))
        return b"x"

    await cache.cached_payload("t", "ev-6", "p", compute)
    assert seen_locks[0] is not None
    assert f"{key}:lock" not in fake_redis.data
