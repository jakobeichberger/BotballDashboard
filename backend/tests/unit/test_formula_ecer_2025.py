"""Acceptance test: the default formula sets must reproduce ECER 2025 exactly.

The fixtures below are the published results from `docs/assets/Results 2025.xlsx`
— raw inputs on the left, the officially scored values on the right. If a change
to the formula engine or to the default formula sets ever alters a real
tournament result, these tests fail.

Formulas come from the Botball Game Review and the ECER 2025 amendments; see
DEFAULT_FORMULA_SETS for the citations.
"""

import pytest

from modules.scoring.formula_engine import DEFAULT_FORMULA_SETS, run_formula_set

# Bracket weighting is announced per tournament ("Note #2" in the game review).
# ECER 2025 used 1.0 for bracket A and this value for bracket B.
BRACKET_B_WEIGHT = 0.5683760683760684

# name, seed_runs, bracket, de_rank, paper, p1, p2, p3, seed_score, de_score, overall
BOTBALL_2025 = [
    (
        "SKP - Skilled Penguins",
        [149.0, 289.0, 518.0],
        "A",
        1,
        73.0,
        100.0,
        100.0,
        100.0,
        0.9175664451827242,
        1.0,
        2.7825664451827246,
    ),
    (
        "AXHT 3085/3",
        [602.0, 18.0, 18.0],
        "A",
        3,
        100.0,
        98.0,
        100.0,
        100.0,
        0.7849875415282392,
        0.7142857142857143,
        2.4959399224806202,
    ),
    (
        "NotImplementedException",
        [35.0, 194.0, 514.0],
        "A",
        2,
        0.0,
        69.0,
        100.0,
        100.0,
        0.8501349667774086,
        0.8571428571428572,
        2.155611157253599,
    ),
    (
        "F2P",
        [32.0, 44.0, 46.0],
        "B",
        4,
        92.0,
        100.0,
        100.0,
        100.0,
        0.44056270764119604,
        0.3789173789173789,
        1.779480086558575,
    ),
    (
        "2nd place",
        [17.0, 36.0, 8.0],
        "B",
        2,
        92.5,
        100.0,
        100.0,
        100.0,
        0.2922549833887043,
        0.5052231718898386,
        1.7599781552785427,
    ),
    (
        "RoBo Masters",
        [44.0, 31.0, 15.0],
        "B",
        1,
        55.0,
        98.0,
        100.0,
        100.0,
        0.3905730897009967,
        0.5683760683760684,
        1.7306158247437318,
    ),
    (
        "LiTec-ME",
        [198.0, 8.0, 31.0],
        "A",
        5,
        43.0,
        94.0,
        100.0,
        100.0,
        0.5162998338870431,
        0.4285714285714286,
        1.6498712624584717,
    ),
    (
        "HTL St. Johann",
        [377.0, 8.0, 160.0],
        "A",
        5,
        40.5,
        0.0,
        15.5,
        50.0,
        0.7208783222591362,
        0.4285714285714286,
        1.4611164174972315,
    ),
    (
        "Kukuk",
        [34.0, 32.0, 34.0],
        "B",
        5,
        65.0,
        41.0,
        100.0,
        100.0,
        0.34224460132890366,
        0.3157644824311491,
        1.3846757504267193,
    ),
    (
        "Titan",
        [90.0, 233.0, 189.0],
        "A",
        4,
        0.0,
        0.0,
        0.0,
        0.0,
        0.650124584717608,
        0.5714285714285714,
        1.2215531561461794,
    ),
    (
        "HexCat",
        [13.0, 9.0, 11.0],
        "B",
        7,
        82.0,
        96.0,
        100.0,
        100.0,
        0.09873338870431894,
        0.18945868945868946,
        1.1915254114963418,
    ),
    (
        "Hamstinator",
        [0.0, 13.0, 16.0],
        "B",
        7,
        42.0,
        100.0,
        100.0,
        100.0,
        0.14664659468438537,
        0.18945868945868946,
        1.0461052841430747,
    ),
    (
        "100Sachen80",
        [13.0, 0.0, 17.0],
        "B",
        5,
        17.0,
        94.0,
        100.0,
        60.0,
        0.19372923588039867,
        0.3157644824311491,
        1.017827051644881,
    ),
    (
        "Venti",
        [0.0, 20.0, 22.0],
        "B",
        9,
        33.5,
        100.0,
        100.0,
        100.0,
        0.24309593023255813,
        0.06315289648622985,
        0.9737488267187879,
    ),
    (
        "Machinarium",
        [15.0, 369.0, 49.0],
        "A",
        7,
        0.0,
        84.0,
        0.0,
        0.0,
        0.6024190199335548,
        0.1428571428571429,
        0.8852761627906978,
    ),
    (
        "HTL Saalfelden",
        [8.0, 8.0, 11.0],
        "B",
        3,
        0.0,
        78.5,
        85.0,
        60.0,
        0.05082018272425249,
        0.4420702754036087,
        0.8653904581278611,
    ),
]

# name, seed_runs, de_rank, paper, seed_score, de_score, overall
OPEN_2025 = [
    (
        "Mendeljeff",
        [375.0, 54.0, 380.0],
        2,
        77.5,
        0.9757775119617225,
        0.8333333333333334,
        1.8091108452950557,
    ),
    ("Cheese Wizards", [0.0, 418.0, 46.0], 1, 87.5, 0.763755980861244, 1.0, 1.763755980861244),
    (
        "Snackkarotten",
        [369.0, 21.0, 15.0],
        3,
        66.0,
        0.6166267942583732,
        0.6666666666666667,
        1.28329346092504,
    ),
    (
        "Pfusch am Bot",
        [9.0, 24.0, 165.0],
        5,
        73.0,
        0.43151913875598086,
        0.33333333333333337,
        0.7648524720893142,
    ),
    ("French Bakery", [13.0, 14.0, 14.0], 4, 0.0, 0.2583732057416268, 0.5, 0.7583732057416268),
    (
        "GGOpen",
        [8.0, 7.0, 11.0],
        5,
        0.0,
        0.13068181818181815,
        0.33333333333333337,
        0.4640151515151515,
    ),
]

# Aerial 2025 was ranked on the mean of all four runs.
AERIAL_2025 = [
    ("Flying Hirsch", [350.0, 330.0, 160.0, 150.0], 247.5),
    ("SkilledFighters", [175.0, 80.0, 70.0, 65.0], 97.5),
    ("Die Dronaten", [30.0, 30.0, 30.0, 20.0], 27.5),
    ("GGAerial", [160.0, 30.0, 20.0, 10.0], 55.0),
    ("Rieleck Prime", [310.0, 70.0, 50.0, 30.0], 115.0),
    ("BRG Gröhrmühlgasse", [330.0, 330.0, 330.0, 210.0], 300.0),
    ("CrazyDrone", [135.0, 115.0, 65.0, 65.0], 95.0),
    ("LAVAdrone", [60.0, 30.0, 30.0, 20.0], 35.0),
    ("TGM Arial", [170.0, 170.0, 60.0, 50.0], 112.5),
]


OPEN_SHEET_FORMULAS = [
    ("seed_total", "avg_best(seed_runs, 2)"),
    (
        "seed_score",
        "3/4 * ((n - rank(seed_total) + 1) / n) + 1/4 * safe_div(seed_total, max_all(seed_runs))",
    ),
    ("de_score", "safe_div(n - de_rank + 1, n) if de_rank > 0 else 0"),
    ("overall", "seed_score + de_score"),
]


def _botball_rows():
    sizes = {b: sum(1 for r in BOTBALL_2025 if r[2] == b) for b in ("A", "B")}
    return [
        {
            "team_id": name,
            "seed_runs": runs,
            "de_rank": de_rank,
            "n_bracket": sizes[bracket],
            "bracket_weight": 1.0 if bracket == "A" else BRACKET_B_WEIGHT,
            "paper": paper,
            "doc_p1": p1,
            "doc_p2": p2,
            "doc_p3": p3,
        }
        for name, runs, bracket, de_rank, paper, p1, p2, p3, *_ in BOTBALL_2025
    ]


@pytest.fixture(scope="module")
def result():
    res = run_formula_set(DEFAULT_FORMULA_SETS["botball"], _botball_rows())
    assert res.ok, res.issues
    return {r["team_id"]: r for r in res.rows}


@pytest.fixture(scope="module")
def open_result():
    rows = [
        {"team_id": name, "seed_runs": runs, "de_rank": de_rank, "paper": paper}
        for name, runs, de_rank, paper, *_ in OPEN_2025
    ]
    res = run_formula_set(OPEN_SHEET_FORMULAS, rows)
    assert res.ok, res.issues
    return {r["team_id"]: r for r in res.rows}


class TestBotball2025:
    @pytest.mark.parametrize("case", BOTBALL_2025, ids=lambda c: c[0])
    def test_matches_the_published_result(self, result, case):
        name, _, _, _, _, _, _, _, seed_score, de_score, overall = case
        row = result[name]
        assert row["seed_score"] == pytest.approx(seed_score, abs=1e-12)
        assert row["de_score"] == pytest.approx(de_score, abs=1e-12)
        assert row["overall"] == pytest.approx(overall, abs=1e-12)

    def test_final_standings_are_in_the_published_order(self, result):
        ranked = sorted(result.values(), key=lambda r: r["overall"], reverse=True)
        assert [r["team_id"] for r in ranked] == [c[0] for c in BOTBALL_2025]

    def test_seeding_score_stays_within_zero_and_one(self, result):
        assert all(0.0 <= r["seed_score"] <= 1.0 for r in result.values())

    def test_overall_stays_within_zero_and_three(self, result):
        """The game review states the overall score is between 0 and 3 at regionals."""
        assert all(0.0 <= r["overall"] <= 3.0 for r in result.values())

    def test_max_tournament_seed_score_is_the_best_single_run(self, result):
        """The 1/4 term divides by the best single run in the field (602), not the best average."""
        axht = result["AXHT 3085/3"]
        rank_term = 3 / 4 * ((16 - 3 + 1) / 16)
        assert axht["seed_score"] - rank_term == pytest.approx(1 / 4 * (310.0 / 602.0), abs=1e-12)


class TestOpen2025:
    """The published Open sheet scored overall as seeding + DE, without the paper."""

    @pytest.mark.parametrize("case", OPEN_2025, ids=lambda c: c[0])
    def test_matches_the_published_result(self, open_result, case):
        name, _, _, _, seed_score, de_score, overall = case
        row = open_result[name]
        assert row["seed_score"] == pytest.approx(seed_score, abs=1e-12)
        assert row["de_score"] == pytest.approx(de_score, abs=1e-12)
        assert row["overall"] == pytest.approx(overall, abs=1e-12)

    def test_default_open_set_adds_half_the_paper_score(self):
        """The ECER amendment defines Open as DE + Seeding + 1/2 PaperScore."""
        rows = [
            {
                "team_id": name,
                "seed_runs": runs,
                "de_rank": de_rank,
                "n_bracket": len(OPEN_2025),
                "bracket_weight": 1.0,
                "paper": paper,
            }
            for name, runs, de_rank, paper, *_ in OPEN_2025
        ]
        res = run_formula_set(DEFAULT_FORMULA_SETS["open"], rows)
        assert res.ok, res.issues
        mendeljeff = next(r for r in res.rows if r["team_id"] == "Mendeljeff")
        assert mendeljeff["overall"] == pytest.approx(
            0.9757775119617225 + 0.8333333333333334 + 0.5 * 0.775, abs=1e-12
        )


class TestAerial2025:
    @pytest.mark.parametrize("case", AERIAL_2025, ids=lambda c: c[0])
    def test_score_is_the_mean_of_all_runs(self, case):
        name, runs, expected = case
        rows = [{"team_id": n, "aerial_runs": r} for n, r, _ in AERIAL_2025]
        res = run_formula_set(DEFAULT_FORMULA_SETS["aerial"], rows)
        assert res.ok, res.issues
        row = next(r for r in res.rows if r["team_id"] == name)
        assert row["aerial_score"] == pytest.approx(expected, abs=1e-12)

    def test_ranking_order_matches_the_published_sheet(self):
        rows = [{"team_id": n, "aerial_runs": r} for n, r, _ in AERIAL_2025]
        res = run_formula_set(DEFAULT_FORMULA_SETS["aerial"], rows)
        ranked = sorted(res.rows, key=lambda r: r["aerial_score"], reverse=True)
        expected = [n for n, _, _ in sorted(AERIAL_2025, key=lambda c: c[2], reverse=True)]
        assert [r["team_id"] for r in ranked] == expected
