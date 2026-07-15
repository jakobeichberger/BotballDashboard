"""Unit tests for the seasons service layer.

Covers every public function in modules/seasons/service.py:
list_seasons, get_season, get_active_season, create_season, update_season,
set_active_season, delete_season (active-season guard), activate_phase,
list_competition_levels.
"""
import pytest
from sqlalchemy import select

from core.exceptions import ConflictError, NotFoundError
from modules.seasons import service
from modules.seasons.models import CompetitionLevel, Season, SeasonPhase


async def _phases_for(db, season_id):
    """Read phase rows directly.

    The shared test session uses autoflush=False and the create_* service
    helpers never commit, so the freshly-created parent object exposes a
    stale (empty) `phases` collection. The child rows are nonetheless inserted
    on flush, so we query them directly to assert on what was persisted.
    """
    result = await db.execute(
        select(SeasonPhase).where(SeasonPhase.season_id == season_id)
        .order_by(SeasonPhase.sort_order)
    )
    return list(result.scalars().all())


# ── create_season ─────────────────────────────────────────────────────────────

class TestCreateSeason:
    @pytest.mark.asyncio
    async def test_create_minimal(self, db):
        s = await service.create_season(db, {"name": "S1", "year": 2026}, [])
        assert s.id is not None
        assert s.name == "S1"
        assert s.year == 2026
        # Default module toggles come from model defaults after flush
        assert s.phases == []

    @pytest.mark.asyncio
    async def test_create_with_phases(self, db):
        phases = [
            {"name": "Seeding", "phase_type": "seeding", "sort_order": 0},
            {"name": "Finals", "phase_type": "final", "sort_order": 1},
        ]
        s = await service.create_season(db, {"name": "S2", "year": 2027}, phases)
        await db.flush()
        rows = await _phases_for(db, s.id)
        assert len(rows) == 2
        # ordered by sort_order
        assert rows[0].name == "Seeding"
        assert rows[1].name == "Finals"

    @pytest.mark.asyncio
    async def test_create_with_modules(self, db):
        data = {
            "name": "S3",
            "year": 2028,
            "use_double_elimination": True,
            "use_paper_scoring": True,
            "active_categories": ["botball", "open"],
        }
        s = await service.create_season(db, data, [])
        assert s.use_double_elimination is True
        assert s.use_paper_scoring is True
        assert s.active_categories == ["botball", "open"]


# ── list_seasons ──────────────────────────────────────────────────────────────

class TestListSeasons:
    @pytest.mark.asyncio
    async def test_empty(self, db):
        assert await service.list_seasons(db) == []

    @pytest.mark.asyncio
    async def test_ordered_by_year_desc(self, db):
        await service.create_season(db, {"name": "Old", "year": 2020}, [])
        await service.create_season(db, {"name": "New", "year": 2030}, [])
        await service.create_season(db, {"name": "Mid", "year": 2025}, [])
        await db.flush()
        seasons = await service.list_seasons(db)
        years = [s.year for s in seasons]
        assert years == [2030, 2025, 2020]

    @pytest.mark.asyncio
    async def test_includes_existing_fixture(self, db, season):
        seasons = await service.list_seasons(db)
        assert any(s.id == season.id for s in seasons)


# ── get_season ────────────────────────────────────────────────────────────────

class TestGetSeason:
    @pytest.mark.asyncio
    async def test_found(self, db, season):
        fetched = await service.get_season(db, season.id)
        assert fetched.id == season.id
        assert fetched.name == season.name

    @pytest.mark.asyncio
    async def test_not_found_raises(self, db):
        with pytest.raises(NotFoundError):
            await service.get_season(db, "does-not-exist")


# ── get_active_season ─────────────────────────────────────────────────────────

class TestGetActiveSeason:
    @pytest.mark.asyncio
    async def test_none_when_no_active(self, db):
        await service.create_season(db, {"name": "Inactive", "year": 2026}, [])
        await db.flush()
        assert await service.get_active_season(db) is None

    @pytest.mark.asyncio
    async def test_returns_active(self, db, season):
        active = await service.get_active_season(db)
        assert active is not None
        assert active.id == season.id


# ── update_season ─────────────────────────────────────────────────────────────

class TestUpdateSeason:
    @pytest.mark.asyncio
    async def test_update_name(self, db, season):
        updated = await service.update_season(db, season.id, name="Renamed")
        assert updated.name == "Renamed"

    @pytest.mark.asyncio
    async def test_none_values_ignored(self, db, season):
        original = season.name
        updated = await service.update_season(db, season.id, name=None, game_theme="Theme X")
        # name=None must NOT overwrite the existing name
        assert updated.name == original
        assert updated.game_theme == "Theme X"

    @pytest.mark.asyncio
    async def test_update_modules(self, db, season):
        updated = await service.update_season(db, season.id, use_aerial=True,
                                              active_categories=["aerial"])
        assert updated.use_aerial is True
        assert updated.active_categories == ["aerial"]

    @pytest.mark.asyncio
    async def test_update_not_found(self, db):
        with pytest.raises(NotFoundError):
            await service.update_season(db, "missing", name="X")


# ── set_active_season ─────────────────────────────────────────────────────────

class TestSetActiveSeason:
    @pytest.mark.asyncio
    async def test_activate(self, db):
        s = await service.create_season(db, {"name": "A", "year": 2026}, [])
        await db.flush()
        activated = await service.set_active_season(db, s.id)
        assert activated.is_active is True

    @pytest.mark.asyncio
    async def test_deactivates_others(self, db, season):
        # `season` fixture is already active. Create a second one and activate it.
        other = await service.create_season(db, {"name": "Other", "year": 2027}, [])
        await db.flush()
        await service.set_active_season(db, other.id)
        await db.flush()

        active = await service.get_active_season(db)
        assert active.id == other.id
        # Original fixture season is now inactive
        refetched = await service.get_season(db, season.id)
        assert refetched.is_active is False

    @pytest.mark.asyncio
    async def test_activate_not_found(self, db):
        with pytest.raises(NotFoundError):
            await service.set_active_season(db, "missing")


# ── delete_season (active-season guard) ───────────────────────────────────────

class TestDeleteSeason:
    @pytest.mark.asyncio
    async def test_delete_inactive(self, db):
        s = await service.create_season(db, {"name": "Del", "year": 2026}, [])
        await db.flush()
        sid = s.id
        await service.delete_season(db, sid)
        await db.flush()
        with pytest.raises(NotFoundError):
            await service.get_season(db, sid)

    @pytest.mark.asyncio
    async def test_delete_active_raises_conflict(self, db, season):
        # The `season` fixture is active → guard should reject deletion
        with pytest.raises(ConflictError):
            await service.delete_season(db, season.id)

    @pytest.mark.asyncio
    async def test_delete_not_found(self, db):
        with pytest.raises(NotFoundError):
            await service.delete_season(db, "missing")


# ── activate_phase ────────────────────────────────────────────────────────────

class TestActivatePhase:
    @pytest.mark.asyncio
    async def test_activate_single_phase(self, db):
        s = await service.create_season(
            db,
            {"name": "P", "year": 2026},
            [{"name": "Seeding", "phase_type": "seeding", "sort_order": 0}],
        )
        await db.flush()
        phase_id = (await _phases_for(db, s.id))[0].id
        activated = await service.activate_phase(db, s.id, phase_id)
        assert activated.is_active is True

    @pytest.mark.asyncio
    async def test_activate_deactivates_other_phases(self, db):
        s = await service.create_season(
            db,
            {"name": "P2", "year": 2026},
            [
                {"name": "Seeding", "phase_type": "seeding", "sort_order": 0},
                {"name": "Finals", "phase_type": "final", "sort_order": 1},
            ],
        )
        await db.flush()
        seeding, finals = await _phases_for(db, s.id)

        await service.activate_phase(db, s.id, seeding.id)
        await db.flush()
        await service.activate_phase(db, s.id, finals.id)
        await db.flush()

        # Re-read phase rows to confirm only finals is active
        rows = await _phases_for(db, s.id)
        active = [p for p in rows if p.is_active]
        assert len(active) == 1
        assert active[0].id == finals.id

    @pytest.mark.asyncio
    async def test_phase_not_found_raises(self, db):
        s = await service.create_season(db, {"name": "P3", "year": 2026}, [])
        await db.flush()
        with pytest.raises(NotFoundError):
            await service.activate_phase(db, s.id, "missing-phase")

    @pytest.mark.asyncio
    async def test_phase_from_other_season_not_found(self, db):
        s1 = await service.create_season(
            db, {"name": "One", "year": 2026},
            [{"name": "Ph", "phase_type": "seeding"}],
        )
        s2 = await service.create_season(db, {"name": "Two", "year": 2027}, [])
        await db.flush()
        phase_id = (await _phases_for(db, s1.id))[0].id
        # The phase belongs to s1, so activating it under s2 must fail
        with pytest.raises(NotFoundError):
            await service.activate_phase(db, s2.id, phase_id)


# ── list_competition_levels ───────────────────────────────────────────────────

class TestListCompetitionLevels:
    @pytest.mark.asyncio
    async def test_empty(self, db):
        assert await service.list_competition_levels(db) == []

    @pytest.mark.asyncio
    async def test_only_active_returned_and_ordered(self, db):
        db.add_all([
            CompetitionLevel(name="GCER", code="gcer", is_active=True),
            CompetitionLevel(name="ECER", code="ecer", is_active=True),
            CompetitionLevel(name="Hidden", code="hidden", is_active=False),
        ])
        await db.flush()
        levels = await service.list_competition_levels(db)
        names = [lvl.name for lvl in levels]
        # Inactive filtered out, ordered by name ascending
        assert names == ["ECER", "GCER"]
