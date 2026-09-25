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


@pytest.mark.parametrize("template_id", ["botball_2024", "botball_2025", "botball_2026"])
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
