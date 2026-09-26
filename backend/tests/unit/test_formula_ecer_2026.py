"""Acceptance test: the 2026 presets reproduce the official ECER 2026 results.

``fixtures/ecer_2026_results.json`` holds the inputs (seeding runs, DE rank,
paper, documentation periods, aerial runs, JBC points) and the published
values of the official results spreadsheet for every team. The presets run on
the inputs alone; every published score and rank must come out.

Findings pinned here:

* Botball documentation: each period is divided by the best team's points of
  that period, then the three are averaged (not the plain /300 of 2025).
* Seeding and DE ties share a rank (Open: two teams on seeding rank 7).
* Paper ranks are one list over Botball and Open; no paper = score 0.
* The published Open overall is Seeding + DE only, although the 2026 ECER
  amendments state DE + Seeding + ½ Paper (see test_open_overall_as_published).
"""

import json
from pathlib import Path

import pytest

from modules.scoring.formula_engine import (
    FORMULA_PRESETS,
    competition_seed_ranks,
    run_formula_set,
)
from modules.scoring.ranking import competition_ranks
from modules.scoring.service import compute_seed_score

DATA = json.loads((Path(__file__).parent / "fixtures" / "ecer_2026_results.json").read_text())

# The spreadsheet prints ten significant digits.
approx = lambda value: pytest.approx(value, rel=1e-8, abs=1e-9)  # noqa: E731


def _rows(teams: list[dict], *, with_docs: bool) -> list[dict]:
    rows = []
    for team in teams:
        doc = team.get("doc") or [None, None, None]
        rows.append(
            {
                "team_id": team["id"],
                "seed_runs": [float(v) for v in team["seeding"]],
                "de_rank": float(team["de_rank"] or 0),
                # ECER 2026 played one bracket per category.
                "n_bracket": float(len(teams)),
                "bracket_weight": 1.0,
                "paper": float(team["paper"] or 0),
                **(
                    {
                        "doc_p1": float(doc[0] or 0),
                        "doc_p2": float(doc[1] or 0),
                        "doc_p3": float(doc[2] or 0),
                    }
                    if with_docs
                    else {}
                ),
            }
        )
    totals = {r["team_id"]: compute_seed_score(r["seed_runs"]) for r in rows}
    ranks = competition_seed_ranks(totals)
    return [{**r, "seed_rank": ranks[r["team_id"]]} for r in rows]


def _run(preset_id: str, rows: list[dict]) -> dict[str, dict]:
    run = run_formula_set(FORMULA_PRESETS[preset_id].formulas, rows)
    assert run.ok, run.issues
    return {row["team_id"]: row for row in run.rows}


def _ranks(values: dict[str, float]) -> dict[str, int]:
    return competition_ranks(values.items())


BOTBALL = DATA["botball"]
OPEN = DATA["open"]


class TestBotball:
    results = _run("ecer_2026_botball", _rows(BOTBALL, with_docs=True))

    def test_the_fixture_is_the_whole_field(self):
        assert len(BOTBALL) == 18 and len(self.results) == 18

    @pytest.mark.parametrize("team", BOTBALL, ids=lambda t: t["name"])
    def test_every_published_score(self, team):
        row, expected = self.results[team["id"]], team["expected"]
        assert row["seed_total"] == approx(expected["seed_total"])
        assert row["seed_rank"] == expected["seed_rank"]
        assert row["seed_score"] == approx(expected["seed_score"])
        assert row["de_score"] == approx(expected["de_score"])
        assert row["paper_score"] == approx(expected["paper_score"])
        assert row["doc_score"] == approx(expected["doc_score"])
        assert row["adapted_doc_score"] == approx(expected["adapted_doc_score"])
        assert row["overall"] == approx(expected["overall"])

    def test_overall_and_doc_ranks(self):
        overall = _ranks({t: r["overall"] for t, r in self.results.items()})
        adapted = _ranks({t: r["adapted_doc_score"] for t, r in self.results.items()})
        for team in BOTBALL:
            assert overall[team["id"]] == team["expected"]["overall_rank"], team["name"]
            assert adapted[team["id"]] == team["expected"]["adapted_doc_rank"], team["name"]

    def test_documentation_is_relative_to_the_best_team_per_period(self):
        # ProbablyLast: (4/54 + 85/85 + 60/94) / 3 — the 2025 formula would
        # give (4 + 85 + 60) / 300 instead.
        team = next(t for t in BOTBALL if t["name"] == "ProbablyLast")
        assert self.results[team["id"]]["doc_score"] == approx((4 / 54 + 1 + 60 / 94) / 3)
        assert self.results[team["id"]]["doc_score"] != approx(149 / 300)


class TestOpen:
    amendments = _run("ecer_2026_open", _rows(OPEN, with_docs=False))

    @pytest.mark.parametrize("team", OPEN, ids=lambda t: t["name"])
    def test_seeding_and_de(self, team):
        row, expected = self.amendments[team["id"]], team["expected"]
        assert row["seed_rank"] == expected["seed_rank"]
        assert row["seed_score"] == approx(expected["seed_score"])
        assert row["de_score"] == approx(expected["de_score"])

    def test_seeding_ties_share_the_rank(self):
        ranks = {t["name"]: self.amendments[t["id"]]["seed_rank"] for t in OPEN}
        assert ranks["Abmeldekommando"] == ranks["Cyber Warrior III"] == 7

    def test_open_overall_as_published(self):
        """The published Open overall leaves the paper out.

        The amendments (and the ecer_2026_open preset) add ½ · PaperScore;
        the results sheet ranks on Seeding + DE. Kept as a documented
        difference: an organiser who wants the published numbers loads the
        ecer_2026_open_results preset instead.
        """
        published = {}
        for team in OPEN:
            row = self.amendments[team["id"]]
            assert team["expected"]["overall"] == approx(row["seed_score"] + row["de_score"])
            assert row["overall"] == approx(
                row["seed_score"] + row["de_score"] + 0.5 * row["paper_score"]
            )
            published[team["id"]] = row["seed_score"] + row["de_score"]
        ranks = _ranks(published)
        for team in OPEN:
            assert ranks[team["id"]] == team["expected"]["overall_rank"], team["name"]


class TestAlternativeReadings:
    """Both readings of the two points where amendments and results disagree."""

    def test_open_results_preset_reproduces_the_published_open_ranking(self):
        results = _run("ecer_2026_open_results", _rows(OPEN, with_docs=False))
        for team in OPEN:
            assert results[team["id"]]["overall"] == approx(team["expected"]["overall"])
        ranks = _ranks({t: r["overall"] for t, r in results.items()})
        for team in OPEN:
            assert ranks[team["id"]] == team["expected"]["overall_rank"], team["name"]

    def test_rubric_preset_uses_the_rubric_maximum_per_period(self):
        rows = [
            {**row, "doc_p1_max": 100.0, "doc_p2_max": 95.0, "doc_p3_max": 100.0}
            for row in _rows(BOTBALL, with_docs=True)
        ]
        results = _run("ecer_2026_botball_rubric", rows)
        # ProbablyLast: (4/100 + 85/95 + 60/100) / 3 instead of the best-team reading.
        team = next(t for t in BOTBALL if t["name"] == "ProbablyLast")
        assert results[team["id"]]["doc_score"] == approx((4 / 100 + 85 / 95 + 60 / 100) / 3)
        # Seeding and DE are the same in both readings.
        published = _run("ecer_2026_botball", _rows(BOTBALL, with_docs=True))
        for t in BOTBALL:
            assert results[t["id"]]["seed_score"] == approx(published[t["id"]]["seed_score"])


def test_paper_rank_is_one_list_over_botball_and_open():
    papers = {t["id"]: float(t["paper"] or 0) for t in BOTBALL + OPEN}
    ranks = _ranks(papers)
    for team in BOTBALL + OPEN:
        assert ranks[team["id"]] == team["expected"]["paper_rank"], team["name"]


@pytest.mark.parametrize("team", DATA["aerial"], ids=lambda t: t["name"])
def test_aerial_is_the_mean_of_the_best_three_runs(team):
    rows = [
        {"team_id": t["id"], "aerial_runs": [float(r) for r in t["runs"]]} for t in DATA["aerial"]
    ]
    results = _run("aerial_2026", rows)
    assert results[team["id"]]["aerial_score"] == approx(team["score"])
    ranks = _ranks({t: r["aerial_score"] for t, r in results.items()})
    assert ranks[team["id"]] == team["rank"]


def test_jbc_ranks_on_points_for_solved_challenges():
    rows = [{"team_id": t["id"], "jbc_points": float(t["points"])} for t in DATA["jbc"]]
    results = _run("jbc_2026", rows)
    ranks = _ranks({t: r["overall"] for t, r in results.items()})
    for team in DATA["jbc"]:
        assert results[team["id"]]["overall"] == team["points"]
        assert ranks[team["id"]] == team["rank"], team["name"]
