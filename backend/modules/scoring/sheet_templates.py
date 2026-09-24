"""Score-sheet templates transcribed from the official Botball game documents.

Offered in the schema editor as a starting point for a new schema version
(``GET /scoring/schema-templates``). Sources, all in ``docs/assets``:

* 2024 – "2024 Botball Score Sheet.pdf" (Moon Base) and the scoring rules of
  "2024 Botball Game Review v1.0" (rule 7: one area multiplier per area).
* 2025 – "2025 Botball Seeding Score Sheet.pdf" (Restaurant). The Beverage
  Station holds Cups and Water Bottles; Ice and Drinks belong to the Cups
  area (the module spec had these swapped, see audit section E).
* 2026 – "2026 Botball Game Review v1.3" (Warehouse). The review names the
  scoring areas, multipliers and tie-breakers but not the point values; those
  are only on the graphical score sheet, which is not in the repository. The
  template therefore carries the structure with every point value and factor
  set to 1 and is flagged ``complete: False`` — enter the values from the
  official sheet before activating it.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


def _count(key: str, label: str, multiplier: float, max_value: float | None = None) -> dict:
    return {
        "key": key,
        "label": label,
        "type": "count",
        "multiplier": multiplier,
        "min_value": 0,
        "max_value": max_value,
        "required": False,
    }


def _bool(key: str, label: str, multiplier: float) -> dict:
    field = _count(key, label, multiplier, 1)
    field["type"] = "boolean"
    return field


def _flag(key: str, label: str, factor: float) -> dict:
    """A checkbox multiplier: checked multiplies the subtotal by ``factor``."""
    return {"key": key, "label": label, "type": "boolean", "factor": factor, "max_value": 1}


def _times(
    key: str, label: str, factor: float = 1, offset: float = 0, max_value: float | None = None
) -> dict:
    """A counted multiplier: subtotal × (value × factor + offset)."""
    return {
        "key": key,
        "label": label,
        "type": "count",
        "factor": factor,
        "offset": offset,
        "min_value": 0,
        "max_value": max_value,
    }


def _either(key: str, label: str, *options: dict) -> dict:
    return {"key": key, "label": label, "either": list(options)}


def _section(key: str, label: str, fields: list[dict], multipliers: list[dict] | None = None):
    return {"key": key, "label": label, "fields": fields, "multipliers": multipliers or []}


# ── 2024 – Moon Base ──────────────────────────────────────────────────────────


def _area_2024(key: str, label: str) -> dict:
    return _section(
        key,
        label,
        [
            _count(f"{key}_sorted_poms", "Sorted Poms", 5),
            _count(f"{key}_other_pieces", "All Other Game Pieces", 1),
        ],
        [_flag(f"{key}_botguy_cube", "Botguy or Cube in Zone", 5)],
    )


BOTBALL_2024: dict[str, Any] = {
    "sides": ["A", "B"],
    "sections": [
        _area_2024("area1", "Area 1"),
        _area_2024("small_rover_bay", "Small Rover Bay"),
        _area_2024("large_rover_bay", "Large Rover Bay"),
        _area_2024("area2", "Area 2"),
        _area_2024("area3", "Area 3"),
        _area_2024("area4", "Area 4"),
        _area_2024("area5", "Area 5"),
        _area_2024("area6", "Area 6"),
        _section(
            "rock_heap",
            "Rock Heap",
            [
                _count("rock_heap_only_rocks", "Only Rocks", 6, 12),
                _count("rock_heap_other_pieces", "All Other Game Pieces", 1),
            ],
            [_flag("rock_heap_botguy_cube", "Botguy or Cube in Zone", 5)],
        ),
        _section(
            "solar_panel",
            "Solar Panel",
            [_count("solar_panel_flipped", "Solar Panel Flipped", 50, 1)],
            [_times("solar_robots_back", "Robots Back in Start Box (×n+1)", 1, 1, 2)],
        ),
        _section(
            "lava_tube",
            "Lava Tube Area",
            [
                _count("lava_purple_in_area", "Purple Noodles in Area", 50, 4),
                _count("lava_purple_in_tubes", "Purple Noodles in Tubes", 100, 4),
                _count("lava_tube_cap", "Lava Tube Cap", 25, 1),
            ],
            [_times("lava_deepest_tube", "Deepest Lava Tube (1, 2 or 3)", 1, 0, 3)],
        ),
        _section(
            "moon_base",
            "Moon Base",
            [
                _count("moon_air_lock_open", "Air Lock Open", 25, 1),
                _count("moon_light_blue_poms", "Light Blue Poms in Air Lock", 15, 10),
                _count("moon_dark_blue_poms", "Dark Blue Poms in Air Lock", 50, 8),
            ],
            [_flag("moon_air_lock_closed", "Air Lock Closed", 3)],
        ),
        _section(
            "habitat",
            "Habitat Construction",
            [_count("habitat_noodles", "Red or Green Noodles", 8, 40)],
            [_times("habitat_posts", "# of Posts with Habitats", 1, 0)],
        ),
        _section(
            "astronauts",
            "Astronauts",
            [
                _count("astronauts_in_stations", "Astronauts In Stations", 25, 10),
                _count("astronauts_flag_raised", "Flag Raised", 25, 1),
                _count("astronauts_flipped_switch", "Flipped Switch", 20, 1),
            ],
            [_times("astronauts_areas", "# Areas with Astronaut", 1, 0)],
        ),
    ],
}


# ── 2025 – Restaurant ─────────────────────────────────────────────────────────

BOTBALL_2025: dict[str, Any] = {
    "sides": ["A", "B"],
    "sections": [
        _section(
            "prep_station",
            "Starting Box / Prep Station",
            [
                _count("prep_vegetables", "Vegetables", 5, 4),
                _count("prep_botguy", "Botguy", 15, 1),
            ],
            [_flag("prep_botguy_multiplier", "Botguy (×2)", 2)],
        ),
        _section(
            "kitchen_floor",
            "Kitchen Floor",
            [
                _count("kitchen_any_piece", "Any Game Piece", 1),
                _count("kitchen_botguy", "Botguy", 15, 1),
            ],
        ),
        _section(
            "condiment_stations",
            "Condiment Stations",
            [
                _count("condiment_unsorted_poms", "Unsorted Poms", 1, 36),
                _count("condiment_sorted_poms", "Sorted Poms", 5, 36),
            ],
            [_times("condiment_sorted_stations", "# of Sorted Stations", 1, 0, 3)],
        ),
        _section(
            "serving_station",
            "Serving Station",
            [
                _count("serving_red_pom", "One Red Pom in Tray", 5, 6),
                _count("serving_orange_pom", "One Orange Pom in Tray", 5, 6),
                _count("serving_yellow_pom", "One Yellow Pom in Tray", 5, 6),
                _count("serving_side", "One Side in Tray", 15, 6),
                _count("serving_entree", "One Entree in Tray", 15, 6),
            ],
            [
                _either(
                    "serving_bonus",
                    "# of Full Pom Sets in Trays or # of Full Trays ×2",
                    _times("serving_full_pom_sets", "# of Full Pom Sets in Trays", 1, 0, 6),
                    _times("serving_full_trays", "# of Full Trays (×2)", 2, 0, 6),
                )
            ],
        ),
        _section(
            "cups",
            "Cups",
            [
                _count("cups_ice", "Ice", 10),
                _count("cups_wrong_drink", "Wrong Drink Color", 10),
                _count("cups_matching_drink", "Matching Drink Color", 30),
            ],
            [
                _flag("cups_full_cup", "Full Cup (×2)", 2),
                _flag("cups_two_plus_in_beverage", "2+ Cups in Beverage Station (×2)", 2),
            ],
        ),
        _section(
            "fry_station",
            "Fry Station",
            [_count("fry_potato", "Potato", 50, 2)],
            [_flag("fry_no_fries", "No Fries on Game Surface (×2)", 2)],
        ),
        _section(
            "beverage_station",
            "Beverage Station",
            [
                _count("beverage_cups", "Cups", 5, 6),
                _count("beverage_water_bottles", "Water Bottles", 10, 12),
            ],
            [
                _either(
                    "beverage_bottle_bonus",
                    "5 Water Bottles ×3 or 6 Water Bottles ×6",
                    _flag("beverage_five_bottles", "5 Water Bottles (×3)", 3),
                    _flag("beverage_six_bottles", "6 Water Bottles (×6)", 6),
                )
            ],
        ),
    ],
}


# ── 2026 – Warehouse (structure only) ─────────────────────────────────────────

BOTBALL_2026: dict[str, Any] = {
    "sides": ["A", "B"],
    "sections": [
        _section(
            "warehouse_floor",
            "Warehouse Floor",
            [
                _count("floor_cubes", "Cubes", 1),
                _count("floor_poms", "Unsorted Poms", 1),
                _count("floor_sorted_poms", "Sorted Poms", 1),
                _count("floor_stacked_cubes", "Cubes in Stacks", 1),
            ],
            [_times("floor_sorted_sections", "# of Sorted Sections (poms only)", 1, 0, 6)],
        ),
        _section(
            "packaging_bins",
            "Packaging Bins",
            [
                _count("bins_poms", "Poms in Bins", 1),
                _count("bins_sorted_poms", "Sorted Poms in Bins", 1),
            ],
            [_times("bins_matching", "# of Bins with Matching Poms", 1, 0, 4)],
        ),
        _section(
            "packaging_center",
            "Packaging Center",
            [_count("center_returned_bins", "Returned Packaging Bins", 1, 4)],
        ),
        _section(
            "internal_loading_dock",
            "Internal Loading Dock",
            [
                _count("internal_dock_pallets", "Pallets", 1),
                _count("internal_dock_cubes", "Cubes", 1),
                _count("internal_dock_sorted_cubes", "Sorted Cubes on Pallets", 1),
            ],
        ),
        _section(
            "external_loading_dock",
            "External Loading Dock",
            [
                _count("external_dock_pallets", "Pallets", 1),
                _count("external_dock_cubes", "Cubes", 1),
                _count("external_dock_sorted_cubes", "Sorted Cubes on Pallets", 1),
            ],
        ),
        _section(
            "drum_storage",
            "Drum Storage",
            [_count("drum_pipes_on_posts", "Pipes on Drum Storage Posts", 1, 16)],
        ),
        _section(
            "upper_warehouse",
            "Upper Warehouse",
            [_count("upper_cubes", "Cubes", 1)],
            [_flag("upper_clean_deck", "Clean Deck (all poms removed)", 1)],
        ),
        _section(
            "start_boxes",
            "Start Boxes",
            [
                _count("start_traffic_cones", "Traffic Cones in Start Boxes", 1, 4),
                _bool("start_botguy_upper", "Botguy in Upper Start Box", 1),
                _bool("start_botguy_lower", "Botguy in Lower Start Box", 1),
            ],
        ),
    ],
}


TEMPLATES: dict[str, dict[str, Any]] = {
    "botball_2024": {
        "id": "botball_2024",
        "name": "Botball 2024 – Moon Base",
        "year": 2024,
        "complete": True,
        "source": "2024 Botball Score Sheet",
        "notes": "Seeding score sheet; Total = Side A + Side B.",
        "definition": BOTBALL_2024,
    },
    "botball_2025": {
        "id": "botball_2025",
        "name": "Botball 2025 – Restaurant",
        "year": 2025,
        "complete": True,
        "source": "2025 Botball Seeding Score Sheet",
        "notes": "Seeding score sheet; Total = Side A + Side B.",
        "definition": BOTBALL_2025,
    },
    "botball_2026": {
        "id": "botball_2026",
        "name": "Botball 2026 – Warehouse (structure only)",
        "year": 2026,
        "complete": False,
        "source": "2026 Botball Game Review v1.3",
        "notes": (
            "The game review defines the scoring areas and multipliers but not the point "
            "values. Every value is 1 — enter the points from the official score sheet."
        ),
        "definition": BOTBALL_2026,
    },
}


def list_templates() -> list[dict[str, Any]]:
    return [deepcopy(t) for t in TEMPLATES.values()]


def get_template(template_id: str) -> dict[str, Any] | None:
    template = TEMPLATES.get(template_id)
    return deepcopy(template) if template else None
