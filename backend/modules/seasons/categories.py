"""Category registry of a season.

A category is what a team competes in: Botball, ECER Open, Aerial Junior,
Aerial Senior, Junior Botball Challenge, or anything an organiser adds. Team
and event registrations, formula sets, bracket weights and rankings refer to
it by ``key``; the registry adds the labels (DE/EN), the ``kind`` that decides
which results the category has, and its scoring defaults.

A season that has not configured a registry uses ``DEFAULT_CATEGORIES``. The
historical keys stay valid: ``botball``, ``open``, ``aerial`` (Aerial Senior)
and ``jbc``; ``aerial_junior`` is new.
"""

from __future__ import annotations

from collections import Counter
from typing import Annotated, Any

from pydantic import StringConstraints
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.exceptions import ConflictError, ValidationError
from modules.seasons.lifecycle import ensure_writable
from modules.seasons.models import SeasonCategory

#: What a category's results are made of:
#: botball – seeding, DE, documentation, paper; open – seeding, DE, paper;
#: aerial – aerial runs; jbc – points for solved challenges; custom – formulas only.
CATEGORY_KINDS: tuple[str, ...] = ("botball", "open", "aerial", "jbc", "custom")

#: Kinds whose teams play no seeding or head-to-head matches (their results
#: are aerial runs or challenge points). A custom category may score matches.
MATCHLESS_KINDS: frozenset[str] = frozenset({"aerial", "jbc"})

KEY_PATTERN = r"^[a-z][a-z0-9_]{0,19}$"
CategoryKey = Annotated[str, StringConstraints(pattern=KEY_PATTERN)]

_FIELDS = (
    "key",
    "label_de",
    "label_en",
    "kind",
    "formula_preset",
    "run_count",
    "counted_runs",
    "rank_per_bracket",
    "sort_order",
)


def _entry(key: str, label_de: str, label_en: str, kind: str, **extra: Any) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "key": key,
        "label_de": label_de,
        "label_en": label_en,
        "kind": kind,
        "formula_preset": None,
        "run_count": None,
        "counted_runs": None,
        "rank_per_bracket": False,
    }
    entry.update(extra)
    return entry


#: The ECER line-up. "aerial" keeps its historical key and scoring (mean of
#: all runs, ECER 2025); Aerial Junior follows the 2026 rulebook: at least
#: five scoring runs, ranked on the mean of the best three.
DEFAULT_CATEGORIES: tuple[dict[str, Any], ...] = (
    _entry("botball", "Botball", "Botball", "botball"),
    _entry("open", "ECER Open", "ECER Open", "open"),
    _entry(
        "aerial_junior", "Aerial Junior", "Aerial Junior", "aerial", run_count=6, counted_runs=3
    ),
    _entry("aerial", "Aerial Senior", "Aerial Senior", "aerial", run_count=4),
    _entry("jbc", "Junior Botball Challenge", "Junior Botball Challenge", "jbc"),
)


def default_categories() -> list[dict[str, Any]]:
    return [{**entry, "sort_order": index} for index, entry in enumerate(DEFAULT_CATEGORIES)]


def _as_dict(row: SeasonCategory) -> dict[str, Any]:
    return {field: getattr(row, field) for field in _FIELDS}


async def list_categories(db: AsyncSession, season_id: str) -> list[dict[str, Any]]:
    """The season's registry in display order, or the defaults."""
    rows = list(
        (
            await db.execute(
                select(SeasonCategory)
                .where(SeasonCategory.season_id == season_id)
                .order_by(SeasonCategory.sort_order, SeasonCategory.key)
            )
        ).scalars()
    )
    return [_as_dict(row) for row in rows] if rows else default_categories()


async def category_map(db: AsyncSession, season_id: str) -> dict[str, dict[str, Any]]:
    return {entry["key"]: entry for entry in await list_categories(db, season_id)}


def kind_of(categories: dict[str, dict[str, Any]], key: str) -> str:
    """The kind of a category; an unregistered historical key is its own kind."""
    entry = categories.get(key)
    if entry is not None:
        return str(entry["kind"])
    return key if key in CATEGORY_KINDS else "custom"


async def assert_category(db: AsyncSession, season_id: str, key: str | None) -> None:
    """422 unless ``key`` is a category of the season."""
    if key is None:
        return
    categories = await category_map(db, season_id)
    if key not in categories:
        raise ValidationError(
            f"Unknown category '{key}' (allowed: {', '.join(sorted(categories))})"
        )


async def _keys_in_use(db: AsyncSession, season_id: str) -> set[str]:
    from modules.events.models import Event, EventRegistration
    from modules.teams.models import TeamSeasonRegistration

    used = set(
        (
            await db.execute(
                select(TeamSeasonRegistration.category).where(
                    TeamSeasonRegistration.season_id == season_id
                )
            )
        ).scalars()
    )
    used.update(
        (
            await db.execute(
                select(EventRegistration.category)
                .join(Event, Event.id == EventRegistration.event_id)
                .where(Event.season_id == season_id)
            )
        ).scalars()
    )
    return {key for key in used if key}


async def replace_categories(
    db: AsyncSession, season_id: str, entries: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Replace the registry. A key still used by a registration cannot be removed."""
    from modules.scoring.formula_engine import FORMULA_PRESETS

    await ensure_writable(db, season_id=season_id)
    if not entries:
        raise ValidationError("A season needs at least one category")
    duplicates = [k for k, n in Counter(e["key"] for e in entries).items() if n > 1]
    if duplicates:
        raise ValidationError(f"Duplicate category key: {duplicates[0]}")
    for entry in entries:
        if entry["kind"] not in CATEGORY_KINDS:
            raise ValidationError(f"Unknown category kind '{entry['kind']}'")
        preset = entry.get("formula_preset")
        if preset and preset not in FORMULA_PRESETS:
            raise ValidationError(f"Unknown formula preset '{preset}'")
    removed = await _keys_in_use(db, season_id) - {e["key"] for e in entries}
    if removed:
        raise ConflictError(f"Categories still used by registrations: {', '.join(sorted(removed))}")
    await db.execute(delete(SeasonCategory).where(SeasonCategory.season_id == season_id))
    for index, entry in enumerate(entries):
        values = {field: entry.get(field) for field in _FIELDS}
        values["rank_per_bracket"] = bool(values["rank_per_bracket"])
        if values["sort_order"] is None:
            values["sort_order"] = index
        db.add(SeasonCategory(season_id=season_id, **values))
    await db.flush()
    from modules.scoring.service import invalidate_season_rankings

    await invalidate_season_rankings(db, season_id)
    return await list_categories(db, season_id)


async def copy_categories(db: AsyncSession, source_id: str, target_id: str) -> None:
    """Carry a configured registry over to a cloned season."""
    rows = (
        await db.execute(select(SeasonCategory).where(SeasonCategory.season_id == source_id))
    ).scalars()
    for row in rows:
        db.add(SeasonCategory(season_id=target_id, **_as_dict(row)))
