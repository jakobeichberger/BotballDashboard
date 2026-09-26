"""Rescheduling on PostgreSQL, where scheduled_at comes back timezone-aware.

The SQLite suite (tests/integration/test_event_day_paths.py) stores naive
datetimes, so the comparison of a new slot with the stored ones only meets
real ``timestamptz`` values here.
"""

import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from core.config import get_settings
from core.exceptions import ConflictError
from modules.events import service
from modules.events.models import Event
from modules.seasons.models import Season
from modules.teams.models import Team

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_PLATFORM_INTEGRATION") != "1",
    reason="requires explicit PostgreSQL/Redis integration environment",
)

START = datetime(2026, 7, 18, 8, 0, tzinfo=UTC)


@pytest.fixture
async def schedule():
    """Two teams, a seeding phase with two rounds; rolled back afterwards."""
    engine = create_async_engine(get_settings().database_url, poolclass=NullPool)
    async with engine.connect() as connection:
        transaction = await connection.begin()
        db = AsyncSession(bind=connection, expire_on_commit=False)
        tag = uuid.uuid4().hex[:8]
        season = Season(name=f"TZ {tag}", year=2026)
        db.add(season)
        await db.flush()
        event = Event(
            season_id=season.id,
            name=f"TZ {tag}",
            slug=f"tz-{tag}",
            table_count=2,
            active_modules=["seeding"],
        )
        teams = [Team(name=f"TZ {tag} {i}", team_number=f"TZ{tag}{i}") for i in range(2)]
        db.add_all([event, *teams])
        await db.flush()
        for number, team in enumerate(teams, start=1):
            await service.add_registration(
                db, event.id, {"team_id": team.id, "seed_number": number}
            )
        phase = await service.create_phase(
            db, event.id, {"name": "Seeding", "phase_type": "seeding", "sort_order": 0, "rounds": 2}
        )
        matches = await service.generate_schedule(
            db, event.id, {"phase_id": phase.id, "starts_at": START, "slot_minutes": 10}
        )
        try:
            yield db, event, matches
        finally:
            await db.close()
            await transaction.rollback()
    await engine.dispose()


def _team(match) -> str:
    return match.participants[0].team_id


@pytest.mark.asyncio
async def test_conflict_check_with_aware_times(schedule):
    db, event, matches = schedule
    first = next(m for m in matches if m.round_number == 1)
    mover = next(m for m in matches if m.round_number == 2 and _team(m) != _team(first))
    with pytest.raises(ConflictError, match="table and time slot"):
        await service.update_scheduled_match(
            db,
            event.id,
            mover.id,
            {
                "scheduled_at": first.scheduled_at,
                "table_number": first.table_number,
                "expected_version": mover.version,
            },
        )


@pytest.mark.asyncio
async def test_free_slot_with_aware_times(schedule):
    db, event, matches = schedule
    match = matches[0]
    moved = await service.update_scheduled_match(
        db,
        event.id,
        match.id,
        {"scheduled_at": START + timedelta(hours=3), "expected_version": match.version},
    )
    assert moved.scheduled_at == START + timedelta(hours=3)


@pytest.mark.asyncio
async def test_naive_slot_is_not_a_server_error(schedule):
    db, event, matches = schedule
    match = matches[0]
    naive = (START + timedelta(hours=3)).replace(tzinfo=None)
    moved = await service.update_scheduled_match(
        db,
        event.id,
        match.id,
        {"scheduled_at": naive, "table_number": 1, "expected_version": match.version},
    )
    assert moved.scheduled_at is not None
    assert moved.scheduled_at == START + timedelta(hours=3)
