"""Shared Redis clients, live fan-out, cache and outbox claims against real services."""

import asyncio
import os
import uuid
from datetime import UTC, datetime

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import core.live as live
from core import cache, rate_limit, redis_client
from core.config import get_settings

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_PLATFORM_INTEGRATION") != "1",
    reason="requires explicit PostgreSQL/Redis integration environment",
)


@pytest.fixture(autouse=True)
async def fresh_clients():
    # Clients belong to one event loop; every test runs in its own.
    redis_client.reset_clients()
    live._hub = None
    yield
    await redis_client.close_clients()
    live._hub = None


@pytest.mark.asyncio
async def test_rate_limit_script_counts_and_expires():
    bucket = f"ci-{uuid.uuid4().hex[:8]}"
    request = type(
        "R",
        (),
        {
            "app": type("A", (), {"state": type("S", (), {"testing": False})()})(),
            "client": type("C", (), {"host": "10.0.0.1"})(),
        },
    )()
    check = rate_limit.rate_limit(bucket, 2, 30)
    await check(request)
    await check(request)
    with pytest.raises(HTTPException) as denied:
        await check(request)
    assert denied.value.status_code == 429
    ttl = await rate_limit._client().ttl(f"botball:rate:{bucket}:10.0.0.1")
    assert 0 < ttl <= 30


@pytest.mark.asyncio
async def test_rate_limit_repairs_a_counter_without_expiry():
    key = f"botball:rate:ci-{uuid.uuid4().hex[:8]}:10.0.0.2"
    client = rate_limit._client()
    await client.set(key, 5)  # left behind by the old INCR-then-EXPIRE code
    count, ttl = await rate_limit._count(key, 60)
    assert count == 6 and ttl == 60
    assert 0 < await client.ttl(key) <= 60


@pytest.mark.asyncio
async def test_cache_roundtrip_and_version_bump(monkeypatch):
    monkeypatch.setattr(get_settings(), "cache_backend", "redis")
    cache.clear_memory()
    event_id = f"ci-{uuid.uuid4()}"
    computed: list[int] = []

    async def compute() -> bytes:
        computed.append(1)
        return b'[{"n": %d}]' % len(computed)

    first = await cache.cached_payload("t", event_id, "p", compute)
    second = await cache.cached_payload("t", event_id, "p", compute)
    assert first == second and len(computed) == 1
    await cache.bump_version(event_id)
    third = await cache.cached_payload("t", event_id, "p", compute)
    assert third.body == b'[{"n": 2}]' and third.etag != first.etag


@pytest.mark.asyncio
async def test_live_events_reach_subscribers_through_one_subscription():
    event_id = f"ci-{uuid.uuid4()}"
    hub = live.live_hub()
    first = await hub.subscribe(f"botball:live:{event_id}")
    second = await hub.subscribe(f"botball:live:{event_id}")
    other = await hub.subscribe("botball:live:someone-else")
    await asyncio.sleep(0.1)
    assert await live.publish_live_event(event_id, "ranking_updated", {"x": 1})
    for queue in (first, second):
        message = await asyncio.wait_for(queue.get(), 3)
        assert '"ranking_updated"' in message
    assert other.empty()
    # One pattern subscription for the whole process.
    channels = await live._publisher().pubsub_numpat()
    assert channels >= 1
    for channel, queue in (
        (f"botball:live:{event_id}", first),
        (f"botball:live:{event_id}", second),
        ("botball:live:someone-else", other),
    ):
        hub.unsubscribe(channel, queue)


@pytest.mark.asyncio
async def test_concurrent_workers_claim_disjoint_batches():
    from modules.dashboard import tasks
    from modules.dashboard.models import NotificationEvent

    engine = create_async_engine(get_settings().database_url, poolclass=NullPool)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    marker = f"ci-claim-{uuid.uuid4().hex[:8]}"
    try:
        async with factory() as db:
            db.add_all(
                NotificationEvent(event_type=marker, payload={}, created_at=datetime.now(UTC))
                for _ in range(10)
            )
            await db.commit()
        now = datetime.now(UTC)

        async def claim() -> set[str]:
            async with factory() as db:
                items = await tasks.claim_batch(db, now)
                return {item.id for item in items if item.event_type == marker}

        a, b = await asyncio.gather(claim(), claim())
        assert not (a & b)
        assert len(a | b) == 10
    finally:
        async with factory() as db:
            await db.execute(
                delete(NotificationEvent).where(NotificationEvent.event_type == marker)
            )
            await db.commit()
            assert (
                await db.execute(
                    select(NotificationEvent.id).where(NotificationEvent.event_type == marker)
                )
            ).first() is None
        await engine.dispose()
