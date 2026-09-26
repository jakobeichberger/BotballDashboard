"""Row locks that SQLite cannot show: refresh-token rotation, print quota, cache lock.

Each test runs two transactions against the migrated PostgreSQL schema: the
first takes the lock and holds it for a moment, the second arrives meanwhile.
Without ``FOR UPDATE`` the second one reads the old state and both succeed.
"""

import asyncio
import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from core import cache, redis_client
from core.config import get_settings
from core.exceptions import ConflictError, UnauthorizedError

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_PLATFORM_INTEGRATION") != "1",
    reason="requires explicit PostgreSQL/Redis integration environment",
)

HOLD = 0.4


@pytest.fixture
async def factory():
    engine = create_async_engine(get_settings().database_url, poolclass=NullPool)
    yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    await engine.dispose()


@pytest.mark.asyncio
async def test_concurrent_refresh_with_one_token_forks_no_session(factory):
    from core.auth import create_refresh_token
    from modules.auth import service
    from modules.auth.models import RefreshToken, User

    marker = uuid.uuid4().hex[:8]
    async with factory() as db:
        user = User(
            email=f"lock-{marker}@example.com",
            display_name="Lock",
            hashed_password="x",
            is_active=True,
        )
        db.add(user)
        await db.flush()
        token = create_refresh_token(user.id)
        db.add(
            RefreshToken(
                user_id=user.id,
                token_hash=service._hash_token(token),
                expires_at=datetime.now(UTC) + timedelta(days=1),
            )
        )
        await db.commit()
        user_id = user.id

    async def first():
        async with factory() as db:
            pair = await service.refresh_tokens(db, token)
            await asyncio.sleep(HOLD)  # the row stays locked meanwhile
            await db.commit()
            return pair

    async def second():
        await asyncio.sleep(HOLD / 4)
        async with factory() as db:
            try:
                return await service.refresh_tokens(db, token)
            except UnauthorizedError as exc:
                await db.rollback()
                return exc

    try:
        a, b = await asyncio.gather(first(), second())
        assert isinstance(a, tuple)
        # The second refresh waited for the first and then saw a reused token.
        assert isinstance(b, UnauthorizedError)
        async with factory() as db:
            left = (
                await db.execute(select(RefreshToken).where(RefreshToken.user_id == user_id))
            ).all()
            assert left == []  # reuse ended every session, the new chain included
            reloaded = await db.get(User, user_id)
            assert reloaded.token_version == 1
    finally:
        async with factory() as db:
            await db.execute(delete(User).where(User.id == user_id))
            await db.commit()


@pytest.mark.asyncio
async def test_concurrent_print_submissions_respect_the_hard_limit(factory):
    from modules.events.models import Event, EventRegistration
    from modules.printing import service
    from modules.printing.models import PrintJob, TeamSeasonPrintQuota
    from modules.seasons.models import Season
    from modules.teams.models import Team

    marker = uuid.uuid4().hex[:8]
    async with factory() as db:
        season = Season(name=f"Lock {marker}", year=2026, is_active=False, status="active")
        team = Team(name=f"Lock {marker}", team_number=f"L-{marker}", country="AT")
        db.add_all([season, team])
        await db.flush()
        event = Event(season_id=season.id, name="Lock", slug=f"lock-{marker}", status="published")
        db.add(event)
        await db.flush()
        db.add(EventRegistration(event_id=event.id, team_id=team.id))
        db.add(
            TeamSeasonPrintQuota(
                team_id=team.id,
                season_id=season.id,
                event_id=event.id,
                max_parts=1,
                soft_limit_parts=1,
            )
        )
        await db.commit()
        ids = {"season": season.id, "team": team.id, "event": event.id}

    data = {
        "team_id": ids["team"],
        "season_id": ids["season"],
        "event_id": ids["event"],
        "file_name": "part.stl",
    }

    async def first():
        async with factory() as db:
            job = await service.create_print_job(db, data, submitted_by=None)
            await asyncio.sleep(HOLD)
            await db.commit()
            return job

    async def second():
        await asyncio.sleep(HOLD / 4)
        async with factory() as db:
            try:
                job = await service.create_print_job(db, data, submitted_by=None)
                await db.commit()
                return job
            except ConflictError as exc:
                await db.rollback()
                return exc

    try:
        a, b = await asyncio.gather(first(), second())
        assert isinstance(a, PrintJob)
        assert isinstance(b, ConflictError), "both submissions passed the hard limit"
        async with factory() as db:
            jobs = (
                await db.execute(select(PrintJob).where(PrintJob.team_id == ids["team"]))
            ).all()
            assert len(jobs) == 1
    finally:
        async with factory() as db:
            await db.execute(delete(PrintJob).where(PrintJob.team_id == ids["team"]))
            await db.execute(
                delete(TeamSeasonPrintQuota).where(TeamSeasonPrintQuota.team_id == ids["team"])
            )
            await db.execute(
                delete(EventRegistration).where(EventRegistration.team_id == ids["team"])
            )
            await db.execute(delete(Event).where(Event.id == ids["event"]))
            await db.execute(delete(Team).where(Team.id == ids["team"]))
            await db.execute(delete(Season).where(Season.id == ids["season"]))
            await db.commit()


@pytest.mark.asyncio
async def test_cache_lock_lets_one_instance_compute(monkeypatch):
    redis_client.reset_clients()
    monkeypatch.setattr(get_settings(), "cache_backend", "redis")
    cache.clear_memory()
    key = cache._entry_key("t", f"ci-{uuid.uuid4()}", 0, "p")
    calls = 0

    async def compute() -> bytes:
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.2)
        return b"[1]"

    try:
        # Two "instances": the in-process single flight is bypassed on purpose.
        first, second = await asyncio.gather(
            cache._compute_and_store(key, compute), cache._compute_and_store(key, compute)
        )
        assert calls == 1
        assert first == second
        assert await cache._client().get(f"{key}:lock") is None
    finally:
        await redis_client.close_clients()
