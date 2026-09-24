"""The shipped formula presets, checked against the game review by hand.

Like test_formula_ecer_2025, these run the formula engine directly on input
rows, so a change to a preset that alters a documented formula fails here.
"""

import pytest

from modules.scoring.formula_engine import (
    DEFAULT_FORMULA_SETS,
    FORMULA_PRESETS,
    GCER_BOTBALL_FORMULA_SET,
    KNOWN_INPUTS,
    REGIONAL_2026_BOTBALL_FORMULA_SET,
    run_formula_set,
)
from modules.scoring.formula_service import formula_input_names, validate_formula_set


def _row(team_id, *, seed_runs, de_rank=0, n_bracket=0, doc=(0, 0, 0), onsite=0, ds=()):
    double_runs = [float(v) for v in ds]
    return {
        "team_id": team_id,
        "seed_runs": [float(v) for v in seed_runs],
        "de_rank": float(de_rank),
        "n_bracket": float(n_bracket),
        "bracket_weight": 1.0,
        "doc_p1": float(doc[0]),
        "doc_p2": float(doc[1]),
        "doc_p3": float(doc[2]),
        "onsite": float(onsite),
        "paper": 0.0,
        "double_seed_runs": double_runs,
        "double_seed_total": sum(double_runs) / len(double_runs) if double_runs else 0.0,
    }


class TestPresetCatalogue:
    def test_all_requested_presets_exist(self):
        assert set(FORMULA_PRESETS) == {
            "ecer_2025_botball",
            "ecer_2025_open",
            "regional_2026_botball",
            "gcer_2026_botball",
            "aerial",
            "jbc",
        }

    def test_ecer_sets_stay_the_defaults(self):
        assert FORMULA_PRESETS["ecer_2025_botball"].formulas == DEFAULT_FORMULA_SETS["botball"]
        assert FORMULA_PRESETS["ecer_2025_open"].formulas == DEFAULT_FORMULA_SETS["open"]

    @pytest.mark.parametrize("preset_id", sorted(FORMULA_PRESETS))
    def test_every_preset_validates_against_the_documented_inputs(self, preset_id):
        # Only documented inputs — a preset must never need an "unknown variable".
        validate_formula_set(FORMULA_PRESETS[preset_id].formulas, formula_input_names())

    def test_double_seeding_inputs_are_documented(self):
        assert "double_seed_runs" in KNOWN_INPUTS
        assert "double_seed_total" in KNOWN_INPUTS


class TestRegional2026:
    def test_doc_score_weights_and_overall_range(self):
        rows = [
            _row(
                "a",
                seed_runs=[100, 100, 0],
                de_rank=1,
                n_bracket=2,
                doc=(100, 100, 100),
                onsite=100,
            ),
            _row("b", seed_runs=[40, 20, 0], de_rank=2, n_bracket=2, doc=(50, 0, 100), onsite=25),
        ]
        run = run_formula_set(REGIONAL_2026_BOTBALL_FORMULA_SET, rows)
        assert run.ok, run.issues
        a, b = run.rows
        assert a["doc_score"] == pytest.approx(1.0)
        # 0.2·0.5 + 0.2·0 + 0.2·1 + 0.4·0.25
        assert b["doc_score"] == pytest.approx(0.4)
        # DE = (n − rank + 1) / n
        assert a["de_score"] == pytest.approx(1.0)
        assert b["de_score"] == pytest.approx(0.5)
        # Overall = seed + DE + doc, so 0..3 and the winner gets exactly 3.
        assert a["overall"] == pytest.approx(3.0)
        assert 0.0 <= b["overall"] <= 3.0
        assert "paper_score" not in a


class TestGcer2026:
    def test_documentation_is_onsite_only(self):
        rows = [
            _row("a", seed_runs=[100], doc=(0, 0, 0), onsite=80, ds=[10]),
            _row("b", seed_runs=[50], doc=(100, 100, 100), onsite=0, ds=[5]),
        ]
        run = run_formula_set(GCER_BOTBALL_FORMULA_SET, rows)
        assert run.ok, run.issues
        a, b = run.rows
        assert a["doc_score"] == pytest.approx(0.8)
        assert b["doc_score"] == pytest.approx(0.0)

    def test_double_seed_score_uses_every_run(self):
        # Team a: runs 100, 0, 0 → mean 33.3 (no drop); team b: 40, 40, 40 → 40.
        rows = [
            _row("a", seed_runs=[10], ds=[100, 0, 0]),
            _row("b", seed_runs=[10], ds=[40, 40, 40]),
        ]
        run = run_formula_set(GCER_BOTBALL_FORMULA_SET, rows)
        assert run.ok, run.issues
        a, b = run.rows
        n = 2
        # b ranks first on the double-seed average although a has the best run.
        assert b["double_seed_score"] == pytest.approx(2 / 3 * 1.0 + 1 / 3 * (40 / 100))
        assert a["double_seed_score"] == pytest.approx(
            2 / 3 * ((n - 2 + 1) / n) + 1 / 3 * ((100 / 3) / 100)
        )

    def test_overall_is_up_to_four(self):
        rows = [
            _row("a", seed_runs=[100, 100], de_rank=1, n_bracket=1, onsite=100, ds=[50, 50]),
            _row("b", seed_runs=[0], ds=[0]),
        ]
        run = run_formula_set(GCER_BOTBALL_FORMULA_SET, rows)
        assert run.ok, run.issues
        assert run.rows[0]["overall"] == pytest.approx(4.0)
