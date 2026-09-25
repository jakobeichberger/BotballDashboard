"""The documented ECER 2027 example season (modules.seasons.examples)."""

from datetime import date

import pytest

from core.exceptions import ConflictError
from modules.seasons.categories import list_categories
from modules.seasons.examples import create_example_season_2027, example_2027
from modules.seasons.service import list_events


def test_example_payload_matches_the_announcement():
    data = example_2027()
    season = data["season"]
    assert (season["event_start"], season["event_end"]) == (date(2027, 4, 5), date(2027, 4, 9))
    assert season["registration_close"] == date(2026, 12, 15)
    assert season["status"] == "draft"
    assert "Linz" in season["notes"]
    # A copy: callers cannot change the documented data.
    data["season"]["name"] = "changed"
    assert example_2027()["season"]["name"] == "ECER 2027"


@pytest.mark.asyncio
async def test_creates_a_draft_season_once(db):
    season = await create_example_season_2027(db)
    assert season.status == "draft" and not season.is_active
    deadlines = {e.title: e.event_date for e in await list_events(db, season.id)}
    assert deadlines["Botball registration closes"] == date(2026, 12, 15)
    categories = {c["key"]: c for c in await list_categories(db, season.id)}
    assert categories["botball"]["formula_preset"] == "ecer_2026_botball"
    assert categories["aerial_junior"]["counted_runs"] == 3
    with pytest.raises(ConflictError):
        await create_example_season_2027(db)
