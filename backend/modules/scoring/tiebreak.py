"""Tie-breakers and the special round conditions of the Botball game reviews.

Pure functions only — the services feed them rows and persist the results.

A season configures an ordered list of criteria (``ScoringRuleSet.tiebreakers``).
Each criterion takes its per-match value either from the score sheet
(``source="sheet"``: the sum of one or more raw sheet values over both sides,
e.g. "# of full trays") or from a value the juror enters for the match
(``source="entry"``: e.g. "robot closest to Botguy"). ``direction`` says whether
more (``max``) or less (``min``) wins.

Head-to-head (DE / double seeding), from the game review "Tie Breakers &
Special Scoring Conditions":

1. A disqualified team loses.
2. A team that never left its Starting Box, or whose robot did not shut down at
   the end, loses the round. Never leaving the box is the stronger condition:
   a robot that keeps moving does not lose against a team that never left.
3. Higher score wins.
4. On a tie the criteria are applied in order. A criterion marked
   ``replay_only`` (2026: "closest to Botguy") only counts once the match has
   been replayed.
5. Finals (2026): tie-breakers are not used, the match is replayed until one
   team scores more — enabled per season with ``finals_replay``.
"""

from __future__ import annotations

import functools
import math
from dataclasses import dataclass, field
from typing import Any

from modules.scoring import sheet

#: Reserved key in ``Match.tiebreak_values``: truthy when the round is a replay.
REPLAYED_KEY = "replayed"

LOSE_ROUND_REASONS = ("never_left_start_box", "motors_running", "other")


# ── Presets from the game reviews ─────────────────────────────────────────────


def _c(
    key: str,
    label: str,
    *sheet_keys: str,
    direction: str = "max",
    replay_only: bool = False,
) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "direction": direction,
        "source": "sheet" if sheet_keys else "entry",
        "sheet_keys": list(sheet_keys),
        "replay_only": replay_only,
    }


TIEBREAKER_PRESETS: dict[str, dict[str, Any]] = {
    "botball_2024": {
        "name": "Botball 2024 (Game Review v1.0)",
        "finals_replay": False,
        "tiebreakers": [
            _c("ice_in_air_lock", "Most Mixed/Water Ice in the closed Air Lock"),
            _c("areas_with_astronauts", "Most Areas scoring Astronauts", "astronauts_areas"),
            _c("equipment_in_tubes", "Most Equipment inside Lava Tubes", "lava_purple_in_tubes"),
            _c("posts_with_habitats", "Most Construction posts with Habitats", "habitat_posts"),
            _c("habitats_on_posts", "Most Habitats on Construction posts", "habitat_noodles"),
            _c("rocks_in_heap", "Most Lunar Rocks in the Rock Heap", "rock_heap_only_rocks"),
            _c("flag_raised", "Flag raised", "astronauts_flag_raised"),
            _c("surface_habitats", "Most Surface Habitats on own side"),
            _c("botguy_on_side", "Botguy on own side"),
            _c("closest_to_botguy", "Robot closest to Botguy (cm)", direction="min"),
        ],
    },
    "botball_2025": {
        "name": "Botball 2025 (Game Review v1.2)",
        "finals_replay": False,
        "tiebreakers": [
            _c("full_cups", "Largest number of full Cups"),
            _c("full_trays", "Largest number of full Trays", "serving_full_trays"),
            _c(
                "full_pom_sets", "Largest number of full pom sets in Trays", "serving_full_pom_sets"
            ),
            _c("trays_with_entrees", "Largest number of Trays with entrees", "serving_entree"),
            _c("trays_with_sides", "Largest number of Trays with sides", "serving_side"),
            _c(
                "bottles_or_cups",
                "Largest number of Water Bottles or Cups in Beverage Station",
                "beverage_cups",
                "beverage_water_bottles",
            ),
            _c("sorted_poms", "Largest number of sorted poms", "condiment_sorted_poms"),
            _c("potato_in_fry_station", "Potato in Fry Station", "fry_potato"),
            _c("botguy_on_side", "Botguy on own side"),
            _c("kitchen_floor_types", "Most different object types on the Kitchen Floor"),
            _c("closest_to_botguy", "Robot closest to Botguy (cm)", direction="min"),
        ],
    },
    # Game Review v1.4, "Tie Breakers & Special Scoring Conditions" (same
    # order as v1.3). Criteria the score sheet cannot answer (sorted poms in
    # baskets, stack height, …) are entered by the juror for the match.
    "botball_2026": {
        "name": "Botball 2026 (Game Review v1.4)",
        "finals_replay": True,
        "tiebreakers": [
            _c(
                "sorted_cubes_external_dock",
                "Largest number of sorted cubes on the External Loading Docks",
                "external_dock_sorted_cubes",
            ),
            # Sorted cubes on a dock are on a pallet by definition (rule 4a.i);
            # unsorted dock cubes may stand on the dock itself and are left out.
            _c(
                "cubes_on_pallets",
                "Largest number of cubes on pallets",
                "lower_start_box_cubes_on_pallets",
                "upper_start_box_cubes_on_pallets",
                "floor_cubes_on_pallets",
                "internal_dock_sorted_cubes",
                "external_dock_sorted_cubes",
            ),
            _c("sorted_poms_in_baskets", "Largest number of sorted poms in baskets"),
            _c(
                "pipes_on_posts",
                "Largest number of pipes on Drum Storage posts",
                "drum_pipes_unsorted",
                "drum_pipes_sorted",
            ),
            _c(
                "cones_in_start_boxes",
                "Largest number of traffic cones scoring in start boxes",
                "lower_start_box_traffic_cones",
                "upper_start_box_traffic_cones",
            ),
            _c("tallest_stack", "Tallest stack of scored cubes"),
            _c("floor_areas_both_colors", "Most Warehouse Floor Areas with both pom colors"),
            _c("botguy_upper_start_box", "Botguy in Upper Start Box", "upper_start_box_botguy"),
            _c("botguy_lower_start_box", "Botguy in Lower Start Box", "lower_start_box_botguy"),
            _c("floor_object_types", "Most different object types in Warehouse Floor Areas"),
            _c("fewest_on_black_tape", "Fewest game pieces on black tape", direction="min"),
            _c(
                "closest_to_botguy",
                "Robot closest to Botguy (cm) – only after one replay",
                direction="min",
                replay_only=True,
            ),
        ],
    },
}


# ── Criterion values ──────────────────────────────────────────────────────────


def criterion_value(
    criterion: dict[str, Any],
    raw_scores: dict | None,
    tiebreak_values: dict | None,
    definition: dict | None,
) -> float | None:
    """One criterion's value for one match; None when nothing was recorded."""
    if criterion.get("source") == "sheet":
        keys = criterion.get("sheet_keys") or []
        if not keys:
            return None
        return sum(sheet.sheet_value(raw_scores or {}, key, definition) for key in keys)
    value = (tiebreak_values or {}).get(criterion["key"])
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    try:
        return float(value)
    except TypeError, ValueError:
        return None


def match_values(
    criteria: list[dict[str, Any]],
    raw_scores: dict | None,
    tiebreak_values: dict | None,
    definition: dict | None,
) -> dict[str, float | None]:
    return {c["key"]: criterion_value(c, raw_scores, tiebreak_values, definition) for c in criteria}


def sum_values(rows: list[dict[str, float | None]]) -> dict[str, float | None]:
    """Aggregate per-match values of one team (e.g. its counted seeding runs)."""
    out: dict[str, float | None] = {}
    for row in rows:
        for key, value in row.items():
            if value is None:
                out.setdefault(key, None)
            else:
                out[key] = (out.get(key) or 0.0) + value
    return out


def _better(criterion: dict[str, Any], a: float | None, b: float | None) -> int:
    """1 if a wins, -1 if b wins, 0 if the criterion doesn't separate them.

    A recorded value beats a missing one (the juror measured only one robot,
    or only one team scored the item); two missing values are equal.
    """
    if a is None and b is None:
        return 0
    minimize = criterion.get("direction") == "min"
    if a is None:
        return -1 if b is not None else 0
    if b is None:
        return 1
    if a == b:
        return 0
    return (1 if a < b else -1) if minimize else (1 if a > b else -1)


def compare(
    a: dict[str, float | None],
    b: dict[str, float | None],
    criteria: list[dict[str, Any]],
    *,
    replayed: bool = True,
) -> tuple[int, dict[str, Any] | None]:
    """Walk the criteria in order: (1 | -1 | 0, deciding criterion)."""
    for criterion in criteria:
        if criterion.get("replay_only") and not replayed:
            continue
        result = _better(criterion, a.get(criterion["key"]), b.get(criterion["key"]))
        if result:
            return result, criterion
    return 0, None


# ── Ranking ties ──────────────────────────────────────────────────────────────


@dataclass
class RankedItem:
    id: str
    score: float
    values: dict[str, float | None] = field(default_factory=dict)
    fallback: float | None = None  # lower wins, e.g. a seeding rank
    rank: int = 0
    decided_by: str | None = None


def rank_with_tiebreakers(
    items: list[RankedItem],
    criteria: list[dict[str, Any]],
    *,
    fallback_label: str | None = None,
) -> list[RankedItem]:
    """Order by score, then break equal scores with the criteria.

    Items that no criterion (and no fallback) separates share a rank.
    ``decided_by`` names the criterion that placed an item relative to the
    tied item directly before it (for the first of a tie group: after it).
    """

    def fallback(item: RankedItem) -> float:
        # A team without a fallback (no seeding rank) ranks after those with
        # one. Treating it as "equal to everyone" made the comparison
        # non-transitive, so the order depended on the input order.
        return math.inf if item.fallback is None else item.fallback

    def cmp(x: RankedItem, y: RankedItem) -> int:
        if x.score != y.score:
            return -1 if x.score > y.score else 1
        result, _ = compare(x.values, y.values, criteria)
        if result:
            return -result
        if fallback(x) != fallback(y):
            return -1 if fallback(x) < fallback(y) else 1
        return 0

    def separator(x: RankedItem, y: RankedItem) -> str | None:
        _, criterion = compare(x.values, y.values, criteria)
        if criterion:
            return str(criterion.get("label") or criterion["key"])
        if fallback(x) != fallback(y):
            return fallback_label
        return None

    # Items nothing separates keep sharing a rank; listing them by id makes the
    # output independent of the input order.
    ordered = sorted(sorted(items, key=lambda item: item.id), key=functools.cmp_to_key(cmp))
    for position, item in enumerate(ordered, start=1):
        item.decided_by = None
        previous = ordered[position - 2] if position > 1 else None
        following = ordered[position] if position < len(ordered) else None
        if previous is not None and cmp(previous, item) == 0:
            item.rank = previous.rank
        else:
            item.rank = position
        if previous is not None and previous.score == item.score:
            item.decided_by = separator(previous, item)
        elif following is not None and following.score == item.score:
            item.decided_by = separator(item, following)
    return ordered


# ── Head to head ──────────────────────────────────────────────────────────────


@dataclass
class Contestant:
    team_id: str
    total: float
    disqualified: bool = False
    round_lost: bool = False
    round_lost_reason: str | None = None
    values: dict[str, float | None] = field(default_factory=dict)


@dataclass
class Outcome:
    winner: str | None
    reason: str  # disqualified | round_lost | score | tiebreaker | finals_replay | replay
    decided_by: str | None = None
    replay: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "winner": self.winner,
            "reason": self.reason,
            "decided_by": self.decided_by,
            "replay": self.replay,
        }


def decide_head_to_head(
    a: Contestant,
    b: Contestant,
    criteria: list[dict[str, Any]],
    *,
    is_final: bool = False,
    finals_replay: bool = False,
    replayed: bool = False,
) -> Outcome:
    if a.disqualified != b.disqualified:
        return Outcome(b.team_id if a.disqualified else a.team_id, "disqualified")
    if a.disqualified and b.disqualified:
        return Outcome(None, "disqualified", replay=True)

    if a.round_lost != b.round_lost:
        return Outcome(b.team_id if a.round_lost else a.team_id, "round_lost")
    if a.round_lost and b.round_lost:
        a_left = a.round_lost_reason != "never_left_start_box"
        b_left = b.round_lost_reason != "never_left_start_box"
        if a_left != b_left:
            return Outcome(a.team_id if a_left else b.team_id, "round_lost")
        return Outcome(None, "round_lost", replay=True)

    if a.total != b.total:
        return Outcome(a.team_id if a.total > b.total else b.team_id, "score")
    if is_final and finals_replay:
        return Outcome(None, "finals_replay", replay=True)
    result, criterion = compare(a.values, b.values, criteria, replayed=replayed)
    if result:
        label = str(criterion.get("label") or criterion.get("key")) if criterion else None
        return Outcome(a.team_id if result > 0 else b.team_id, "tiebreaker", label)
    return Outcome(None, "replay", replay=True)


def end_contact_bonus(offender_score: float, percent: float = 25.0) -> float:
    """Bonus the opponent receives for intentional end-of-game contact."""
    return round(max(offender_score, 0.0) * percent / 100.0, 2)
