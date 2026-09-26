"""Score-sheet calculation against the fixtures shared with the frontend.

The same file drives frontend/src/__tests__/scoring/calculator.test.ts, so the
backend total and the live preview in the entry form cannot drift apart.
"""

import json
from pathlib import Path

import pytest

from core.exceptions import ValidationError
from modules.scoring import service, sheet
from modules.scoring.sheet_schemas import SheetDefinition
from modules.scoring.sheet_templates import TEMPLATES, list_templates

FIXTURES = (
    Path(__file__).resolve().parents[3]
    / "frontend/src/modules/scoring/sheet/__fixtures__/score-sheet-cases.json"
)
DATA = json.loads(FIXTURES.read_text())


def _schema(name: str) -> tuple[list[dict], dict | None]:
    schema = DATA["schemas"][name]
    return schema.get("fields", []), schema.get("definition")


@pytest.mark.parametrize("case", DATA["cases"], ids=[c["name"] for c in DATA["cases"]])
def test_fixture_case(case):
    fields, definition = _schema(case["schema"])
    if case.get("error"):
        with pytest.raises(ValidationError):
            service.compute_match_total(case["raw"], fields, definition)
        return

    assert service.compute_match_total(case["raw"], fields, definition) == case["total"]

    result = sheet.compute_sheet(case["raw"], sheet.normalize(fields, definition))
    assert result["total"] == case["total"]
    for side, total in case.get("side_totals", {}).items():
        assert next(s for s in result["sides"] if s["side"] == side)["total"] == total
    for path, (subtotal, multiplier, total) in case.get("sections", {}).items():
        side, _, key = path.rpartition(".")
        side_result = next(s for s in result["sides"] if (s["side"] or "") == side)
        section = next(s for s in side_result["sections"] if s["key"] == key)
        assert (section["subtotal"], section["multiplier"], section["total"]) == (
            subtotal,
            multiplier,
            total,
        ), path


@pytest.mark.parametrize(
    "template_id", ["botball_2024", "botball_2025", "botball_2026", "aircer_2026"]
)
def test_fixture_schemas_are_the_shipped_templates(template_id):
    """The frontend fixture embeds the templates; keep them identical."""
    assert DATA["schemas"][template_id]["definition"] == TEMPLATES[template_id]["definition"]


@pytest.mark.parametrize("template", list_templates(), ids=lambda t: t["id"])
def test_templates_are_valid_definitions(template):
    parsed = SheetDefinition.model_validate(template["definition"])
    # Round-tripping through the request model must not change the calculation.
    raw = {item["key"]: 1 for item in sheet.input_fields(template["definition"])}
    assert sheet.compute_total(raw, [], parsed.to_dict()) == sheet.compute_total(
        raw, [], template["definition"]
    )


def test_every_template_is_complete():
    assert all(template["complete"] for template in TEMPLATES.values())


def _points(template_id: str) -> dict[str, dict[str, float]]:
    return {
        section["key"]: {f["key"]: f["multiplier"] for f in section["fields"]}
        for section in TEMPLATES[template_id]["definition"]["sections"]
    }


def test_2026_point_values_match_the_official_sheet():
    """Every itemised value of "2026 Botball Seeding Score Sheet.pdf"."""
    points = _points("botball_2026")
    assert list(points) == [
        "lower_start_box",
        "upper_start_box",
        "warehouse_floor",
        "internal_loading_dock",
        "drum_storage",
        "packaging_bin",
        "upper_warehouse",
        "external_loading_dock",
    ]
    assert list(points["lower_start_box"].values()) == [2, 5, 10, 25, 50, 100]
    assert list(points["upper_start_box"].values()) == [2, 5, 10, 25, 100, 200]
    assert list(points["warehouse_floor"].values()) == [1, 5, 1, 10, 25, 50]
    assert list(points["internal_loading_dock"].values()) == [10, 30]
    assert list(points["drum_storage"].values()) == [100, 200]
    assert list(points["packaging_bin"].values()) == [10, 20, 150]
    assert list(points["upper_warehouse"].values()) == [2, 200, 100]
    assert list(points["external_loading_dock"].values()) == [15, 45]


def test_2026_multipliers_match_the_official_sheet():
    sections = {s["key"]: s for s in TEMPLATES["botball_2026"]["definition"]["sections"]}

    def shape(key):
        return [
            (m.get("source"), m.get("factor"), m.get("offset", 0))
            for m in sections[key]["multipliers"]
        ]

    assert shape("lower_start_box") == [
        ("lower_start_box_drums", 2, 0),
        ("lower_start_box_botguy", 2, 0),
    ]
    assert shape("upper_start_box") == [(None, 1, 2)]  # # of Robots × ___ + 2
    assert shape("warehouse_floor") == [(None, 1, 0)]
    assert shape("internal_loading_dock") == [(None, 1, 0)]
    assert shape("drum_storage") == [(None, 1, 0)]
    assert shape("packaging_bin") == [(None, 1, 1), (None, 1, 0)]  # +1, returned
    assert shape("upper_warehouse") == [(None, 1, 0)]
    assert shape("external_loading_dock") == [(None, 1, 1)]  # pallets + 1


def test_derived_multiplier_has_no_input_and_follows_its_field():
    definition = TEMPLATES["botball_2026"]["definition"]
    keys = {item["key"] for item in sheet.input_fields(definition)}
    assert "A.lower_start_box_drums" in keys
    assert "A.lower_start_box_drum_bonus" not in keys
    with pytest.raises(ValidationError, match="not part of the active scoring schema"):
        sheet.validate({"A.lower_start_box_drum_bonus": True}, [], definition)
    # Botguy elsewhere on the side does not switch on the lower start box bonus.
    assert (
        sheet.compute_total({"A.lower_start_box_poms": 1, "A.floor_botguy": 1}, [], definition)
        == 52
    )


def test_derived_multiplier_must_name_a_field_of_its_section():
    section = {
        "key": "zone",
        "label": "Zone",
        "fields": [{"key": "pieces", "label": "Pieces"}],
        "multipliers": [
            {"key": "bonus", "label": "Bonus", "type": "boolean", "factor": 2, "source": "other"}
        ],
    }
    with pytest.raises(ValueError, match="is not a field of section"):
        SheetDefinition.model_validate({"sections": [section]})
    section["multipliers"][0]["source"] = "pieces"
    parsed = SheetDefinition.model_validate({"sections": [section]}).to_dict()
    assert parsed["sections"][0]["multipliers"][0]["source"] == "pieces"
    assert sheet.compute_total({"pieces": 3}, [], parsed) == 6
    counted = {**section["multipliers"][0], "type": "count"}
    with pytest.raises(ValueError, match="only a checkbox multiplier"):
        SheetDefinition.model_validate({"sections": [{**section, "multipliers": [counted]}]})


def test_multiplier_without_source_keeps_its_stored_shape():
    parsed = SheetDefinition.model_validate(TEMPLATES["botball_2025"]["definition"]).to_dict()
    prep = parsed["sections"][0]["multipliers"][0]
    assert "source" not in prep


def test_2025_beverage_station_holds_cups_and_bottles():
    """Audit E: Ice/drinks belong to the Cups area, not the Beverage Station."""
    sections = {s["key"]: s for s in TEMPLATES["botball_2025"]["definition"]["sections"]}
    assert [f["key"] for f in sections["beverage_station"]["fields"]] == [
        "beverage_cups",
        "beverage_water_bottles",
    ]
    assert "cups_ice" in [f["key"] for f in sections["cups"]["fields"]]


def test_flat_fields_list_every_input_per_side():
    definition = TEMPLATES["botball_2025"]["definition"]
    flat = sheet.flat_fields(definition)
    keys = [f["key"] for f in flat]
    assert "A.fry_potato" in keys and "B.fry_potato" in keys
    assert "A.serving_full_trays" in keys  # either-or options are inputs too
    assert len(keys) == len(set(keys))
    potato = next(f for f in flat if f["key"] == "A.fry_potato")
    assert potato["section"] == "A · Fry Station" and potato["multiplier"] == 50


def test_validate_rejects_unknown_and_out_of_range_keys():
    definition = TEMPLATES["botball_2025"]["definition"]
    sheet.validate({"A.fry_potato": 2, "B.cups_full_cup": True}, [], definition)
    with pytest.raises(ValidationError, match="not part of the active scoring schema"):
        sheet.validate({"fry_potato": 1}, [], definition)
    with pytest.raises(ValidationError, match="at most 3"):
        sheet.validate({"A.condiment_sorted_stations": 4}, [], definition)
    with pytest.raises(ValidationError, match="must be numeric"):
        sheet.validate({"A.fry_potato": "two"}, [], definition)


def test_definition_rejects_duplicate_keys():
    base = {
        "key": "zone",
        "label": "Zone",
        "fields": [{"key": "pieces", "label": "Pieces"}],
        "multipliers": [{"key": "pieces", "label": "Dup", "type": "boolean", "factor": 2}],
    }
    with pytest.raises(ValueError, match="Duplicate field key"):
        SheetDefinition.model_validate({"sections": [base]})
    with pytest.raises(ValueError):
        SheetDefinition.model_validate(
            {
                "sections": [
                    {
                        **base,
                        "multipliers": [
                            {"key": "x", "label": "X", "either": [{"key": "y", "label": "Y"}]}
                        ],
                    }
                ]
            }
        )


# ── AIRCER 2026 and the multiplier options it needs ──────────────────────────


def _aircer_variant(name: str) -> dict:
    return DATA["schemas"][name]["definition"]


def test_aircer_fixture_variants_differ_only_in_their_switch():
    """The "product" and "zero" fixture schemas are the template with one option flipped."""
    base = TEMPLATES["aircer_2026"]["definition"]
    for name, switch, value in (
        ("aircer_2026_product", "mode", "product"),
        ("aircer_2026_zero", "zero_means", "zero"),
    ):
        variant = _aircer_variant(name)
        for base_section, section in zip(base["sections"], variant["sections"], strict=True):
            for base_m, m in zip(base_section["multipliers"], section["multipliers"], strict=True):
                if switch in base_m:
                    assert m[switch] == value, (name, m["key"])
                    assert {**m, switch: base_m[switch]} == base_m
                else:
                    assert m == base_m
        SheetDefinition.model_validate(variant)


def test_aircer_point_values_match_the_official_sheet():
    """Every itemised value of "2026-AIRCER-Scoring-Sheet-1.0.pdf"."""
    points = _points("aircer_2026")
    assert list(points) == [
        "lower_storage_deck",
        "upper_storage_deck",
        "centrifuge",
        "research_table",
        "incineration_plant",
        "research_stations",
        "robot_control",
        "waste_management",
        "laboratory_ground",
    ]
    assert list(points["lower_storage_deck"].values()) == [20, 5, 1]
    assert list(points["upper_storage_deck"].values()) == [20, 10, 1]
    assert list(points["centrifuge"].values()) == [50, 20, 1]
    assert list(points["research_table"].values()) == [15, 5, 1]
    assert list(points["incineration_plant"].values()) == [10, 15, 20, 50]
    assert list(points["research_stations"].values()) == [100]
    assert list(points["robot_control"].values()) == [50]
    assert list(points["waste_management"].values()) == [20, 1]
    assert list(points["laboratory_ground"].values()) == [1]


def test_aircer_is_single_sided_with_the_tiebreaker_keys():
    template = TEMPLATES["aircer_2026"]
    definition = template["definition"]
    assert definition["sides"] == []
    keys = {item["key"] for item in sheet.input_fields(definition)}
    # Package-2 tie-breakers read these keys (most valid drums, rocks, lever).
    assert {
        "centrifuge_sorted_drums",
        "centrifuge_unsorted_drums",
        "waste_rocks",
        "safety_lever",
    } <= keys
    assert all("." not in key for key in keys)
    raw = {"centrifuge_sorted_drums": 3, "centrifuge_unsorted_drums": 2, "safety_lever": True}
    assert sheet.sheet_value(raw, "centrifuge_sorted_drums", definition) == 3
    assert sheet.sheet_value(raw, "safety_lever", definition) == 1
    result = sheet.compute_sheet(raw, definition)
    assert [side["side"] for side in result["sides"]] == [None]
    for word in ("sum", "product", "zero_means", "Unsorted Drums", "Restricted Area"):
        assert word in template["notes"]


def test_sum_multiplier_inputs_replace_its_own_key():
    definition = TEMPLATES["aircer_2026"]["definition"]
    specs = {item["key"]: item for item in sheet.input_fields(definition)}
    assert "upper_deck_stacks" not in specs
    height = specs["upper_deck_max_stack_height"]
    assert (height["role"], height["type"], height["group"]) == (
        "multiplier",
        "count",
        "upper_deck_stacks",
    )
    with pytest.raises(ValidationError, match="not part of the active scoring schema"):
        sheet.validate({"upper_deck_stacks": 3}, [], definition)
    with pytest.raises(ValidationError, match="at most 28"):
        sheet.validate({"research_table_stack_count": 29}, [], definition)


def _one_section(multiplier: dict) -> dict:
    return {
        "sections": [
            {
                "key": "zone",
                "label": "Zone",
                "fields": [{"key": "pieces", "label": "Pieces"}],
                "multipliers": [multiplier],
            }
        ]
    }


def test_sum_multiplier_definition_rules():
    good = {
        "key": "stacks",
        "label": "Stacks",
        "type": "sum",
        "inputs": [{"key": "height", "label": "Height"}, {"key": "count", "label": "Count"}],
    }
    parsed = SheetDefinition.model_validate(_one_section(good)).to_dict()
    stored = parsed["sections"][0]["multipliers"][0]
    # Unset switches stay out of the stored shape; defaults apply.
    assert "mode" not in stored and "zero_means" not in stored
    assert "allow_below_one" not in stored
    assert sheet.compute_total({"pieces": 2, "height": 3, "count": 2}, [], parsed) == 10
    with pytest.raises(ValueError, match="needs at least one input"):
        SheetDefinition.model_validate(_one_section({**good, "inputs": None}))
    with pytest.raises(ValueError, match="only a sum multiplier has inputs"):
        SheetDefinition.model_validate(_one_section({**good, "type": "count"}))
    with pytest.raises(ValueError, match="Duplicate field key"):
        SheetDefinition.model_validate(
            _one_section({**good, "inputs": [{"key": "pieces", "label": "Dup"}]})
        )
    either = {"key": "best", "label": "Best", "either": [good, {"key": "x", "label": "X"}]}
    with pytest.raises(ValueError, match="cannot be an either-or alternative"):
        SheetDefinition.model_validate(_one_section(either))
    with pytest.raises(ValueError, match="counted multipliers only"):
        SheetDefinition.model_validate(
            _one_section({"key": "b", "label": "B", "zero_means": "zero"})
        )


def test_explicit_switches_are_stored_and_legacy_shapes_unchanged():
    parsed = SheetDefinition.model_validate(TEMPLATES["aircer_2026"]["definition"]).to_dict()
    sections = {s["key"]: s for s in parsed["sections"]}
    upper = sections["upper_storage_deck"]["multipliers"][0]
    assert (upper["mode"], upper["zero_means"]) == ("sum", "neutral")
    restricted = sections["incineration_plant"]["multipliers"][1]
    assert restricted["allow_below_one"] is True and restricted["factor"] == 0.5
    new_keys = {"inputs", "mode", "allow_below_one", "zero_means", "source"}
    for template_id in ("botball_2024", "botball_2025"):
        legacy = SheetDefinition.model_validate(TEMPLATES[template_id]["definition"]).to_dict()
        for section in legacy["sections"]:
            for multiplier in section["multipliers"]:
                for option in multiplier.get("either") or [multiplier]:
                    assert not new_keys & option.keys(), option


def test_half_factor_without_allow_below_one_keeps_the_botball_rule():
    definition = _one_section({"key": "half", "label": "Half", "factor": 0.5, "max_value": 1})
    assert sheet.compute_total({"pieces": 4, "half": True}, [], definition) == 4
    definition["sections"][0]["multipliers"][0]["allow_below_one"] = True
    assert sheet.compute_total({"pieces": 4, "half": True}, [], definition) == 2
    assert sheet.compute_total({"pieces": 4, "half": False}, [], definition) == 4
