"""OCR worker: page alignment by anchor marks and validation rules (synthetic scans)."""

from pathlib import Path

import cv2
import numpy as np
import pytest

from modules.scoring.score_sheets.models import ScoreSheetScan, ScoreSheetTemplate
from modules.scoring.score_sheets.scan_service import (
    _align_page,
    apply_validation_rules,
    run_local_ocr,
)
from modules.scoring.score_sheets.schemas import OcrValidationRules, ScoreSheetTemplateLayoutUpdate

PAGE_WIDTH, PAGE_HEIGHT = 800, 1100
ANCHOR = 40
# Filled reference squares near the four corners, normalized like the editor stores them.
ANCHORS = [
    {
        "name": name,
        "x": x / PAGE_WIDTH,
        "y": y / PAGE_HEIGHT,
        "width": ANCHOR / PAGE_WIDTH,
        "height": ANCHOR / PAGE_HEIGHT,
    }
    for name, x, y in (
        ("top_left", 40, 40),
        ("top_right", 720, 40),
        ("bottom_left", 40, 1020),
        ("bottom_right", 720, 1020),
    )
]
MARK = (400, 520, 50, 50)  # a ticked checkbox


def _sheet(*, anchors: bool = True) -> np.ndarray:
    page = np.full((PAGE_HEIGHT, PAGE_WIDTH, 3), 255, dtype=np.uint8)
    if anchors:
        for anchor in ANCHORS:
            x, y = int(anchor["x"] * PAGE_WIDTH), int(anchor["y"] * PAGE_HEIGHT)
            cv2.rectangle(page, (x, y), (x + ANCHOR - 1, y + ANCHOR - 1), (0, 0, 0), -1)
    x, y, w, h = MARK
    cv2.rectangle(page, (x, y), (x + w - 1, y + h - 1), (0, 0, 0), -1)
    # Some printed text and ruled lines the anchor search must ignore.
    cv2.putText(page, "Botball 2026", (200, 200), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 0), 3)
    cv2.line(page, (60, 300), (740, 300), (0, 0, 0), 2)
    return page


def _photograph(page: np.ndarray) -> np.ndarray:
    """The sheet slightly rotated, shrunk and shifted on a larger white background."""
    matrix = cv2.getRotationMatrix2D((PAGE_WIDTH / 2, PAGE_HEIGHT / 2), 2.5, 0.96)
    matrix[:, 2] += (45, 30)
    return cv2.warpAffine(
        page, matrix, (PAGE_WIDTH + 100, PAGE_HEIGHT + 90), borderValue=(255, 255, 255)
    )


def _mark_centre(page: np.ndarray) -> tuple[float, float]:
    x, y, w, h = MARK
    gray = cv2.cvtColor(page, cv2.COLOR_BGR2GRAY)
    window = gray[y - 60 : y + h + 60, x - 60 : x + w + 60] < 128
    ys, xs = np.nonzero(window)
    return x - 60 + xs.mean(), y - 60 + ys.mean()


def test_anchors_undo_rotation_scale_and_shift():
    aligned, method = _align_page(_photograph(_sheet()), PAGE_WIDTH, PAGE_HEIGHT, ANCHORS)
    assert method == "anchors"
    cx, cy = _mark_centre(aligned)
    expected = (MARK[0] + MARK[2] / 2 - 0.5, MARK[1] + MARK[3] / 2 - 0.5)
    assert abs(cx - expected[0]) < 2 and abs(cy - expected[1]) < 2


def test_without_anchors_a_filled_box_is_mistaken_for_the_sheet_edge():
    # The photo shows no sheet edge, so the largest quadrilateral is the ticked
    # box; the contour method blows it up to the whole page. Anchors avoid this.
    aligned, method = _align_page(_photograph(_sheet()), PAGE_WIDTH, PAGE_HEIGHT)
    assert method == "contour"
    assert (cv2.cvtColor(aligned, cv2.COLOR_BGR2GRAY) < 128).mean() > 0.5


def test_three_anchors_suffice_and_pixel_boxes_work():
    pixel_anchors = [
        {
            "name": a["name"],
            "x": a["x"] * PAGE_WIDTH,
            "y": a["y"] * PAGE_HEIGHT,
            "width": ANCHOR,
            "height": ANCHOR,
        }
        for a in ANCHORS[:3]
    ]
    aligned, method = _align_page(_photograph(_sheet()), PAGE_WIDTH, PAGE_HEIGHT, pixel_anchors)
    assert method == "anchors"
    cx, _ = _mark_centre(aligned)
    assert abs(cx - (MARK[0] + MARK[2] / 2)) < 2.5


def test_missing_marks_fall_back_to_the_sheet_edge():
    page = _sheet(anchors=False)
    # A dark background makes the sheet edge the largest quadrilateral.
    scan = np.zeros((PAGE_HEIGHT + 200, PAGE_WIDTH + 200, 3), dtype=np.uint8)
    scan[100 : 100 + PAGE_HEIGHT, 100 : 100 + PAGE_WIDTH] = page
    aligned, method = _align_page(scan, PAGE_WIDTH, PAGE_HEIGHT, ANCHORS)
    assert method == "contour"
    cx, cy = _mark_centre(aligned)
    assert abs(cx - (MARK[0] + MARK[2] / 2)) < 3 and abs(cy - (MARK[1] + MARK[3] / 2)) < 3


def _template(**overrides) -> ScoreSheetTemplate:
    values = {
        "id": "tpl",
        "page_width": PAGE_WIDTH,
        "page_height": PAGE_HEIGHT,
        "anchors": ANCHORS,
        "confirmed_fields": [
            {"key": "parked", "label": "Parked", "type": "boolean"},
            {"key": "docked", "label": "Docked", "type": "boolean"},
        ],
        "field_regions": [
            {"key": "parked", "x": 0.5, "y": 520 / PAGE_HEIGHT, "width": 0.0625, "height": 0.045},
            {"key": "docked", "x": 0.2, "y": 0.8, "width": 0.0625, "height": 0.045},
        ],
        "validation_rules": {"min_confidence": 0.5},
    }
    values.update(overrides)
    return ScoreSheetTemplate(**values)


def _scan(tmp_path: Path, image: np.ndarray) -> ScoreSheetScan:
    path = tmp_path / "scan.png"
    cv2.imwrite(str(path), image)
    return ScoreSheetScan(id="scan", event_id="event", file_url=str(path), file_name=path.name)


def test_worker_reads_the_ticked_box_of_an_anchored_photo(tmp_path):
    values = run_local_ocr(_scan(tmp_path, _photograph(_sheet())), _template())
    by_key = {item["key"]: item for item in values}
    assert by_key["parked"]["value"] is True
    assert by_key["docked"]["value"] is False
    assert by_key["parked"]["reasons"] == []
    assert (tmp_path / "scan" / "crops" / "parked.png").exists()


def test_worker_flags_every_value_when_the_anchors_are_not_found(tmp_path):
    values = run_local_ocr(_scan(tmp_path, _photograph(_sheet(anchors=False))), _template())
    assert all("anchors_not_found" in item["reasons"] for item in values)
    assert all(item["requiresReview"] for item in values)


def test_legacy_rules_that_do_not_validate_fall_back_to_defaults(tmp_path):
    template = _template(anchors=None, validation_rules={"min_confidence": "strict"})
    values = run_local_ocr(_scan(tmp_path, _sheet()), template)
    # Default threshold 0.85 is above the fixed checkbox confidence (0.8).
    assert all("low_confidence" in item["reasons"] for item in values)
    assert not any("anchors_not_found" in item["reasons"] for item in values)


FIELDS = {
    "cubes": {"key": "cubes", "type": "count", "max_value": 10},
    "rings": {"key": "rings", "type": "count", "min_value": 0},
    "parked": {"key": "parked", "type": "boolean"},
}


def _values(**read: float | bool | None) -> list[dict]:
    return [{"key": key, "value": value, "confidence": 0.95} for key, value in read.items()]


def test_rules_tighten_field_limits_and_check_integers():
    rules = OcrValidationRules.model_validate(
        {"fields": [{"key": "cubes", "min_value": 1, "max_value": 6, "integer": True}]}
    )
    low, high, fractional = (
        apply_validation_rules(_values(cubes=v), FIELDS, rules)[0] for v in (0, 7, 2.5)
    )
    assert low["reasons"] == ["below_minimum"]
    assert high["reasons"] == ["above_maximum"]
    assert fractional["reasons"] == ["not_integer"]
    # The field's own maximum (10) still applies where the rule is looser.
    loose = OcrValidationRules.model_validate({"fields": [{"key": "cubes", "max_value": 50}]})
    assert apply_validation_rules(_values(cubes=11), FIELDS, loose)[0]["reasons"] == [
        "above_maximum"
    ]


def test_confidence_threshold_is_configurable_per_template_and_field():
    values = [{"key": "cubes", "value": 3, "confidence": 0.7}]
    lenient = OcrValidationRules(min_confidence=0.6)
    assert apply_validation_rules(values, FIELDS, lenient)[0]["requiresReview"] is False
    strict_field = OcrValidationRules.model_validate(
        {"min_confidence": 0.6, "fields": [{"key": "cubes", "min_confidence": 0.9}]}
    )
    result = apply_validation_rules(values, FIELDS, strict_field)[0]
    assert result["reasons"] == ["low_confidence"]
    assert result["requiresReview"] is True


def test_sum_rules_flag_every_member_but_not_other_fields():
    rules = OcrValidationRules.model_validate(
        {"sums": [{"label": "Objects", "keys": ["cubes", "rings"], "max_value": 8}]}
    )
    values = apply_validation_rules(_values(cubes=5, rings=4, parked=True), FIELDS, rules)
    assert [item["reasons"] for item in values] == [["sum_out_of_range"]] * 2 + [[]]
    ok = apply_validation_rules(_values(cubes=5, rings=3, parked=True), FIELDS, rules)
    assert not any(item["requiresReview"] for item in ok)


def test_empty_values_are_flagged_and_booleans_skip_numeric_limits():
    rules = OcrValidationRules.model_validate({"fields": [{"key": "parked", "max_value": 0}]})
    values = apply_validation_rules(_values(cubes=None, parked=True), FIELDS, rules)
    assert values[0]["reasons"] == ["empty"]
    assert values[1]["reasons"] == []


@pytest.mark.parametrize(
    "rules",
    [
        {"fields": [{"key": "cubes", "min_value": 5, "max_value": 1}]},
        {"fields": [{"key": "cubes"}, {"key": "cubes"}]},
        {"sums": [{"label": "S", "keys": ["cubes", "rings"]}]},
        {"sums": [{"label": "S", "keys": ["cubes", "cubes"], "max_value": 3}]},
        {"min_confidence": 1.5},
    ],
)
def test_inconsistent_rules_are_rejected(rules):
    with pytest.raises(ValueError):
        ScoreSheetTemplateLayoutUpdate.model_validate(
            {
                "page_width": 800,
                "page_height": 1100,
                "field_regions": [
                    {"key": "cubes", "x": 0.1, "y": 0.1, "width": 0.1, "height": 0.1}
                ],
                "validation_rules": rules,
            }
        )
