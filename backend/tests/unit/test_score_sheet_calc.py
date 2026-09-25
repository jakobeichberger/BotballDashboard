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


@pytest.mark.parametrize("template_id", ["botball_2024", "botball_2025"])
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


def test_2026_template_is_flagged_incomplete():
    assert TEMPLATES["botball_2026"]["complete"] is False
    assert TEMPLATES["botball_2024"]["complete"] and TEMPLATES["botball_2025"]["complete"]


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
