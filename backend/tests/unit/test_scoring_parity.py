"""One set of documentation, aerial and bracket cases for every implementation.

The fixture is shared with the frontend preview (frontend/src/lib/scoring.ts,
tested by frontend/src/__tests__/lib/scoring.test.ts). Here the stored-score
helpers of competition_service and the formula presets that compute the same
values must both agree with it.
"""

import json
from pathlib import Path

import pytest

from modules.scoring.competition_service import aerial_score, bracket_score, documentation_score
from modules.scoring.formula_engine import (
    DEFAULT_FORMULA_SETS,
    REGIONAL_2026_BOTBALL_FORMULA_SET,
    run_formula_set,
)

REPO = Path(__file__).resolve().parents[3]
FIXTURE = REPO / "frontend" / "src" / "__tests__" / "lib" / "scoring-parity.json"
CASES = json.loads(FIXTURE.read_text())


def _formula(formula_set: list[tuple[str, str]], key: str) -> tuple[str, str]:
    return next(item for item in formula_set if item[0] == key)


@pytest.mark.parametrize("case", CASES["documentation"], ids=lambda c: str(c["parts"]))
def test_documentation_score(case):
    parts = case["parts"]
    expected = case["score"]
    limits = case.get("maxima", [100, 100, 100, 100])
    maxima = dict(zip(("p1", "p2", "p3", "onsite"), map(float, limits), strict=True))
    result = documentation_score(*parts, maxima=maxima)
    if expected is None:
        assert result is None
        return
    assert result == pytest.approx(expected)

    # The regional preset computes the same score inside the overall ranking.
    names = ("doc_p1", "doc_p2", "doc_p3", "onsite")
    row = dict(
        team_id="t",
        **{name: float(value or 0) for name, value in zip(names, parts, strict=True)},
        **{f"{name}_max": float(limit) for name, limit in zip(names, limits, strict=True)},
    )
    run = run_formula_set([_formula(REGIONAL_2026_BOTBALL_FORMULA_SET, "doc_score")], [row])
    assert not run.issues
    assert run.rows[0]["doc_score"] == pytest.approx(expected)


@pytest.mark.parametrize("case", CASES["aerial"], ids=lambda c: str(c["runs"]))
def test_aerial_score(case):
    runs = case["runs"]
    expected = case["score"]
    counted = case.get("counted")
    result = aerial_score(runs, counted)
    if expected is None:
        assert result is None
        return
    assert result == pytest.approx(expected)

    # The default aerial set counts the category's configured runs (0 = all).
    row = {
        "team_id": "t",
        "aerial_runs": [float(r) for r in runs if r is not None],
        "aerial_counted_runs": float(counted or 0),
    }
    run = run_formula_set([_formula(DEFAULT_FORMULA_SETS["aerial"], "aerial_score")], [row])
    assert not run.issues
    assert run.rows[0]["aerial_score"] == pytest.approx(expected)


@pytest.mark.parametrize("case", CASES["bracket"], ids=lambda c: f"n={c['n']},rank={c['de_rank']}")
def test_bracket_score(case):
    assert bracket_score(case["n"], case["de_rank"]) == pytest.approx(case["score"])

    row = {"team_id": "t", "n_bracket": float(case["n"]), "de_rank": float(case["de_rank"])}
    run = run_formula_set([_formula(DEFAULT_FORMULA_SETS["botball"], "de_bracket_score")], [row])
    assert not run.issues
    assert run.rows[0]["de_bracket_score"] == pytest.approx(case["score"])
