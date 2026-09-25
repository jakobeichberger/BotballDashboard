"""Documented example data: the ECER 2027 season.

What ecer.eraa.at announced (September 2026): ECER 2027 takes place
5–9 April 2027 at the Linzer Technikum, Linz (Austria), organised by ERAA;
Botball registration closes on 15 December 2026 (equipment ships from the
USA); game documents and the Call for Papers follow in January 2027.

Nothing here runs by itself. ``backend/scripts/example_season_2027.py``
prints the payload or, with ``--apply``, creates the season as a *draft* —
an organiser reviews it (dates, categories, formula presets) before
activating it. The game theme and the 2027 formulas are not published yet;
the categories start from the ECER 2026 presets and must be checked against
the 2027 amendments.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.exceptions import ConflictError
from modules.seasons.models import Season

ECER_2027: dict[str, Any] = {
    "season": {
        "name": "ECER 2027",
        "year": 2027,
        "game_theme": None,
        "status": "draft",
        "registration_close": date(2026, 12, 15),
        "event_start": date(2027, 4, 5),
        "event_end": date(2027, 4, 9),
        "notes": (
            "ECER 2027, Linzer Technikum, Paul-Hahn-Straße 4, 4020 Linz. "
            "Organised by ERAA (https://ecer.eraa.at). Botball registration closes "
            "15 December 2026; game documents and Call for Papers January 2027."
        ),
        "use_seeding": True,
        "use_double_elimination": True,
        "use_paper_scoring": True,
        "use_documentation_scoring": True,
        "use_aerial": True,
        "active_categories": ["botball", "open", "aerial_junior", "aerial", "jbc"],
    },
    # The event phases (DE, alliance) are set up per event in the event setup.
    "phases": [{"name": "Seeding", "phase_type": "seeding", "sort_order": 0, "rounds": 3}],
    "deadlines": [
        {
            "title": "Botball registration closes",
            "event_type": "deadline",
            "event_date": date(2026, 12, 15),
            "description": "Equipment ships from the USA; other tracks follow with registration.",
        },
        {
            "title": "ECER 2027 (Linz)",
            "event_type": "event",
            "event_date": date(2027, 4, 5),
            "description": "5–9 April 2027, Linzer Technikum.",
        },
    ],
    # Starting point: the ECER 2026 scoring, to be checked against the 2027
    # amendments once they are published.
    "categories": [
        {
            "key": "botball",
            "label_de": "Botball",
            "label_en": "Botball",
            "kind": "botball",
            "formula_preset": "ecer_2026_botball",
        },
        {
            "key": "open",
            "label_de": "ECER Open",
            "label_en": "ECER Open",
            "kind": "open",
            "formula_preset": "ecer_2026_open",
        },
        {
            "key": "aerial_junior",
            "label_de": "Aerial Junior",
            "label_en": "Aerial Junior",
            "kind": "aerial",
            "formula_preset": "aerial_2026",
            "run_count": 6,
            "counted_runs": 3,
        },
        {
            "key": "aerial",
            "label_de": "Aerial Senior",
            "label_en": "Aerial Senior",
            "kind": "aerial",
            "run_count": 6,
        },
        {
            "key": "jbc",
            "label_de": "Junior Botball Challenge",
            "label_en": "Junior Botball Challenge",
            "kind": "jbc",
            "formula_preset": "jbc_2026",
        },
    ],
}


def example_2027() -> dict[str, Any]:
    return deepcopy(ECER_2027)


async def create_example_season_2027(db: AsyncSession) -> Season:
    """Create the documented ECER 2027 season as a draft (refused if it exists)."""
    from modules.seasons import service
    from modules.seasons.categories import replace_categories

    data = example_2027()
    existing = await db.execute(
        select(Season.id).where(Season.year == 2027, Season.name == data["season"]["name"])
    )
    if existing.first() is not None:
        raise ConflictError("A season 'ECER 2027' already exists")
    season = await service.create_season(db, data["season"], data["phases"])
    for deadline in data["deadlines"]:
        await service.create_event(db, season.id, deadline)
    await replace_categories(db, season.id, data["categories"])
    return season
