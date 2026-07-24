"""Regression tests for the "active row" lookups.

Both used scalar_one_or_none() on queries that can legitimately match more than
one row, so a single bad row made the endpoint fail permanently with
MultipleResultsFound.
"""

import pytest


class TestActiveSeason:
    @pytest.mark.asyncio
    async def test_two_active_seasons_do_not_break_lookup(self, db):
        from modules.seasons.models import Season
        from modules.seasons.service import get_active_season

        db.add_all(
            [
                Season(name="S2025", year=2025, is_active=True),
                Season(name="S2026", year=2026, is_active=True),
            ]
        )
        await db.flush()

        active = await get_active_season(db)
        assert active is not None
        assert active.name == "S2026"  # newest wins

    @pytest.mark.asyncio
    async def test_patch_is_active_deactivates_the_previous_season(self, db):
        from modules.seasons.models import Season
        from modules.seasons.service import get_active_season, update_season

        old = Season(name="Old", year=2025, is_active=True)
        new = Season(name="New", year=2026, is_active=False)
        db.add_all([old, new])
        await db.flush()

        await update_season(db, new.id, is_active=True)
        await db.flush()

        assert old.is_active is False
        assert (await get_active_season(db)).name == "New"


class TestActiveScoringSchema:
    @pytest.mark.asyncio
    async def test_two_active_schemas_return_highest_version(self, db, season):
        from modules.scoring.models import ScoringSchema
        from modules.scoring.service import get_active_schema

        db.add_all(
            [
                ScoringSchema(season_id=season.id, version=1, is_active=True, fields=[]),
                ScoringSchema(season_id=season.id, version=2, is_active=True, fields=[]),
            ]
        )
        await db.flush()

        schema = await get_active_schema(db, season.id)
        assert schema is not None
        assert schema.version == 2


class TestSeasonPhases:
    @pytest.mark.asyncio
    async def test_created_season_response_includes_phases(self, client, auth_headers):
        """Phases are added after the season flush, so they need their own flush."""
        resp = await client.post(
            "/api/seasons",
            headers=auth_headers,
            json={
                "name": "Botball 2027",
                "year": 2027,
                "phases": [{"name": "Seeding", "phase_type": "seeding", "sort_order": 0}],
            },
        )
        assert resp.status_code == 201, resp.text
        assert [p["name"] for p in resp.json()["phases"]] == ["Seeding"]
