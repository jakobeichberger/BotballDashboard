"""Runs a set of scoring formulas over every team in a category.

`formula.py` owns the expression language; this module applies it to a
tournament: it feeds each team's raw inputs in, resolves the evaluation order,
and exposes each computed column to the scope functions (rank, max_all, …) so
later formulas can rank against earlier ones.

DEFAULT_FORMULA_SETS holds the formulas exactly as the game documents state
them — see the docstrings there for the source of each one.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from modules.scoring.formula import (
    FormulaError,
    ParsedFormula,
    ScopeContext,
    evaluate,
    parse_formula,
    resolve_order,
)
from modules.scoring.ranking import competition_ranks

#: A saved set has to stay reviewable and cheap to evaluate for every team.
MAX_FORMULAS_PER_SET = 60


@dataclass
class FormulaIssue:
    key: str
    team_id: str | None
    message: str


@dataclass
class FormulaRunResult:
    """Computed values per team plus anything that went wrong."""

    rows: list[dict[str, Any]] = field(default_factory=list)
    order: list[str] = field(default_factory=list)
    issues: list[FormulaIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues


def _as_floats(value: Any) -> list[float]:
    if value is None:
        return []
    if isinstance(value, list | tuple):
        out: list[float] = []
        for v in value:
            out.extend(_as_floats(v))
        return out
    if isinstance(value, bool):
        return [float(value)]
    if isinstance(value, int | float):
        return [float(value)]
    return []


def run_formula_set(
    formulas: Sequence[tuple[str, str]],
    rows: Sequence[dict[str, Any]],
    *,
    team_id_key: str = "team_id",
) -> FormulaRunResult:
    """Evaluate `formulas` for every row.

    `formulas` is a sequence of (key, expression) in any order — dependencies
    are resolved here. Each row is a team's raw inputs; computed values are
    written back into a copy of it.

    `n` is injected automatically as the number of teams in scope. Anything
    else a formula needs (n_bracket, bracket_weight, …) must be supplied by the
    caller, because only it knows how teams are grouped.
    """
    result = FormulaRunResult()
    if len(formulas) > MAX_FORMULAS_PER_SET:
        result.issues.append(
            FormulaIssue(
                key="",
                team_id=None,
                message=(f"Too many formulas ({len(formulas)}, limit is {MAX_FORMULAS_PER_SET})"),
            )
        )
        result.rows = [dict(r) for r in rows]
        return result

    working = [dict(r) for r in rows]
    for r in working:
        r.setdefault("n", float(len(working)))

    parsed: list[ParsedFormula] = []
    for key, expression in formulas:
        try:
            parsed.append(parse_formula(key, expression))
        except FormulaError as exc:
            result.issues.append(FormulaIssue(key=key, team_id=None, message=str(exc)))
    if result.issues:
        result.rows = working
        return result

    # Columns start out holding the raw inputs so scope functions can reach
    # them (max_all(seed_runs) needs every run of every team).
    columns: dict[str, list[float]] = {}
    for r in working:
        for k, v in r.items():
            columns.setdefault(k, []).extend(_as_floats(v))

    inputs = set(columns)
    try:
        ordered = resolve_order(parsed, inputs)
    except FormulaError as exc:
        result.issues.append(FormulaIssue(key="", team_id=None, message=str(exc)))
        result.rows = working
        return result

    # One context for the whole run: its aggregates and sort orders are built
    # once per column and reused for every team.
    scope = ScopeContext(columns)

    for p in ordered:
        computed: list[float] = []
        for row in working:
            try:
                value = evaluate(p, row, scope)
            except FormulaError as exc:
                result.issues.append(
                    FormulaIssue(key=p.key, team_id=row.get(team_id_key), message=str(exc))
                )
                value = 0.0
            row[p.key] = value
            computed.append(value)
        # Publish the finished column before moving on, so the next formula can
        # rank against it.
        columns[p.key] = computed
        result.order.append(p.key)

    result.rows = working
    return result


# ── Default formula sets ──────────────────────────────────────────────────────
#
# Sources (all in docs/assets):
#   * "Botball Game Review" (2025 v1.2 / 2026 v1.4), section
#     "Overall Winner Calculations":
#         SeedScore = 3/4·((n − SeedRank + 1)/n)
#                   + 1/4·(TeamAverageSeedScore / MaxTournamentSeedScore)
#         DoubleEliminationScore = (n − DERank + 1)/n
#         DocScore  = 2/10·P1% + 2/10·P2% + 2/10·P3% + 4/10·Onsite%
#         Overall   = Seeding + DE + Documentation
#   * "ECER Amendments" (2025 v1.1, 2026 v1.0): no Onsite at ECER, so the
#     three period documentations are rescaled to sum to 1, and the paper
#     halves the weight of the documentation score:
#         DocScore         = 1/3·P1 + 1/3·P2 + 1/3·P3
#         AdaptedDocScore  = 1/2·DocScore + 1/2·PaperScore
#         Overall (Botball)= DE + Seeding + AdaptedDocScore
#         Overall (Open)   = DE + Seeding + 1/2·PaperScore
#   * Official ECER 2026 results: each period is expressed relative to the
#     best team of that period (P1 54/54 = 1, P2 85/85 = 1, …) before the
#     three are averaged; tests/unit/test_formula_ecer_2026.py reproduces all
#     18 Botball teams with it.
#   * "Note #2: Weighting of brackets ... will be released at GCER" — hence
#     bracket_weight is an input, not a constant. ECER 2025 used 1.0 for
#     bracket A and ~0.5684 for bracket B.
#   * Aerial Junior Rulebook 2026: "ranked according to the arithmetic mean
#     of their three highest scores achieved in scoring runs"; ECER 2025
#     ranked Aerial on the mean of all runs.
#   * ECER 2026 results, Junior Botball Challenge: "Points for Solved
#     Challenges" and the rank on them.

_SEED_TOTAL = ("seed_total", "avg_best(seed_runs, 2)")
_SEED_SCORE = (
    "seed_score",
    "3/4 * ((n - rank(seed_total) + 1) / n) + 1/4 * safe_div(seed_total, max_all(seed_runs))",
)
# Same formula on the displayed seeding rank: shared on equal seed scores, or
# tie-broken where the season applies tie-breakers to seeding.
_SEED_SCORE_BY_RANK = (
    "seed_score",
    "3/4 * ((n - seed_rank + 1) / n) + 1/4 * safe_div(seed_total, max_all(seed_runs))",
)
_DE_BRACKET_SCORE = (
    "de_bracket_score",
    "safe_div(n_bracket - de_rank + 1, n_bracket) if de_rank > 0 else 0",
)
_DE_SCORE = ("de_score", "de_bracket_score * bracket_weight")
_PAPER_SCORE = ("paper_score", "paper / 100")

DEFAULT_FORMULA_SETS: dict[str, list[tuple[str, str]]] = {
    # ECER Botball: three period docs, no onsite, paper halves the doc weight.
    "botball": [
        _SEED_TOTAL,
        _SEED_SCORE,
        _DE_BRACKET_SCORE,
        _DE_SCORE,
        ("doc_score", "(doc_p1 + doc_p2 + doc_p3) / 300"),
        _PAPER_SCORE,
        ("adapted_doc_score", "0.5 * doc_score + 0.5 * paper_score"),
        ("overall", "seed_score + de_score + adapted_doc_score"),
    ],
    # ECER Open: same seeding and DE, no Botball documentation.
    "open": [
        _SEED_TOTAL,
        _SEED_SCORE,
        _DE_BRACKET_SCORE,
        _DE_SCORE,
        _PAPER_SCORE,
        ("overall", "seed_score + de_score + 0.5 * paper_score"),
    ],
    # Aerial: the runs the category counts (SeasonCategory.counted_runs) —
    # all of them unless configured.
    "aerial": [
        (
            "aerial_score",
            "avg_best(aerial_runs, aerial_counted_runs) if aerial_counted_runs > 0"
            " else avg(aerial_runs)",
        ),
        ("overall", "aerial_score"),
    ],
    # Junior Botball Challenge: seeding only.
    "jbc": [
        _SEED_TOTAL,
        _SEED_SCORE,
        ("overall", "seed_score"),
    ],
    # A category an organiser added: formulas have to be configured.
    "custom": [],
}

# Regional tournaments 2025/2026: the game review formulas unchanged —
# DocScore = 2/10·P1% + 2/10·P2% + 2/10·P3% + 4/10·Onsite%, overall 0..3.
# The percentages are of each period's rubric maximum (2026: P2 is out of 95).
REGIONAL_2026_BOTBALL_FORMULA_SET: list[tuple[str, str]] = [
    _SEED_TOTAL,
    _SEED_SCORE_BY_RANK,
    _DE_BRACKET_SCORE,
    _DE_SCORE,
    (
        "doc_score",
        "0.2 * safe_div(doc_p1, doc_p1_max) + 0.2 * safe_div(doc_p2, doc_p2_max)"
        " + 0.2 * safe_div(doc_p3, doc_p3_max) + 0.4 * safe_div(onsite, onsite_max)",
    ),
    ("overall", "seed_score + de_score + doc_score"),
]

# GCER 2026: "Documentation scores at GCER will only include the Onsite
# Documentation score", plus the double-seeding score, so overall is 0..4.
# Double seeding drops no run: double_seed_total (supplied by the input
# builder) is the mean of all of a team's double-seeding runs.
GCER_BOTBALL_FORMULA_SET: list[tuple[str, str]] = [
    _SEED_TOTAL,
    _SEED_SCORE_BY_RANK,
    _DE_BRACKET_SCORE,
    _DE_SCORE,
    ("doc_score", "safe_div(onsite, onsite_max)"),
    (
        "double_seed_score",
        "2/3 * ((n - rank(double_seed_total) + 1) / n)"
        " + 1/3 * safe_div(double_seed_total, max_all(double_seed_runs))",
    ),
    ("overall", "seed_score + de_score + doc_score + double_seed_score"),
]

# ECER 2026 Botball: the amendments' DocScore with every period relative to
# the best team of that period, as the official results compute it.
ECER_2026_BOTBALL_FORMULA_SET: list[tuple[str, str]] = [
    _SEED_TOTAL,
    _SEED_SCORE_BY_RANK,
    _DE_BRACKET_SCORE,
    _DE_SCORE,
    (
        "doc_score",
        "(safe_div(doc_p1, max_all(doc_p1)) + safe_div(doc_p2, max_all(doc_p2))"
        " + safe_div(doc_p3, max_all(doc_p3))) / 3",
    ),
    _PAPER_SCORE,
    ("adapted_doc_score", "0.5 * doc_score + 0.5 * paper_score"),
    ("overall", "seed_score + de_score + adapted_doc_score"),
]

# ECER 2026 Open, as the amendments state it: DE + Seeding + ½ Paper.
ECER_2026_OPEN_FORMULA_SET: list[tuple[str, str]] = [
    _SEED_TOTAL,
    _SEED_SCORE_BY_RANK,
    _DE_BRACKET_SCORE,
    _DE_SCORE,
    _PAPER_SCORE,
    ("overall", "seed_score + de_score + 0.5 * paper_score"),
]

AERIAL_2025_FORMULA_SET: list[tuple[str, str]] = [
    ("aerial_score", "avg(aerial_runs)"),
    ("overall", "aerial_score"),
]

AERIAL_2026_FORMULA_SET: list[tuple[str, str]] = [
    ("aerial_score", "avg_best(aerial_runs, 3)"),
    ("overall", "aerial_score"),
]

JBC_2026_FORMULA_SET: list[tuple[str, str]] = [
    ("jbc_score", "jbc_points"),
    ("overall", "jbc_score"),
]


@dataclass(frozen=True)
class FormulaPreset:
    """A ready-made formula set an admin can load into a season's category.

    ``category`` is the category *kind* it is written for (botball, open,
    aerial, jbc); it can be loaded into any category of that kind.
    """

    id: str
    label: str
    category: str
    description: str
    formulas: list[tuple[str, str]]


FORMULA_PRESETS: dict[str, FormulaPreset] = {
    p.id: p
    for p in (
        FormulaPreset(
            "ecer_2026_botball",
            "ECER 2026 – Botball",
            "botball",
            "ECER amendments 2026: P1–P3 each relative to the best team, averaged; "
            "paper halves the doc weight (AdaptedDocScore).",
            ECER_2026_BOTBALL_FORMULA_SET,
        ),
        FormulaPreset(
            "ecer_2026_open",
            "ECER 2026 – ECER Open",
            "open",
            "ECER amendments 2026: Seeding + DE + ½ paper score.",
            ECER_2026_OPEN_FORMULA_SET,
        ),
        FormulaPreset(
            "ecer_2025_botball",
            "ECER 2025 – Botball",
            "botball",
            "Game review + ECER amendments: P1–P3 without onsite, paper halves the doc weight.",
            DEFAULT_FORMULA_SETS["botball"],
        ),
        FormulaPreset(
            "ecer_2025_open",
            "ECER 2025 – ECER Open",
            "open",
            "Seeding + DE + ½ paper score (named PRIA Open in the 2025/2026 amendments).",
            DEFAULT_FORMULA_SETS["open"],
        ),
        FormulaPreset(
            "regional_2026_botball",
            "Regional 2025/2026 – Botball",
            "botball",
            "Game review: 0.2·P1 + 0.2·P2 + 0.2·P3 + 0.4·Onsite of the rubric maxima, overall 0–3.",
            REGIONAL_2026_BOTBALL_FORMULA_SET,
        ),
        FormulaPreset(
            "gcer_2026_botball",
            "GCER 2026 – Botball",
            "botball",
            "Onsite documentation only, plus double seeding (no run dropped), overall 0–4.",
            GCER_BOTBALL_FORMULA_SET,
        ),
        FormulaPreset(
            "aerial_2025",
            "Aerial 2025",
            "aerial",
            "Mean of all aerial runs (ECER 2025).",
            AERIAL_2025_FORMULA_SET,
        ),
        FormulaPreset(
            "aerial_2026",
            "Aerial 2026",
            "aerial",
            "Mean of the best three scoring runs (Aerial Junior Rulebook 2026, ECER 2026).",
            AERIAL_2026_FORMULA_SET,
        ),
        FormulaPreset(
            "jbc",
            "Junior Botball Challenge – seeding",
            "jbc",
            "Seeding only.",
            DEFAULT_FORMULA_SETS["jbc"],
        ),
        FormulaPreset(
            "jbc_2026",
            "Junior Botball Challenge 2026",
            "jbc",
            "Points for solved challenges (ECER 2026).",
            JBC_2026_FORMULA_SET,
        ),
    )
}


def default_formula_set(kind: str, preset_id: str | None = None) -> list[tuple[str, str]]:
    """What a category scores with while the season stores no formulas for it."""
    preset = FORMULA_PRESETS.get(preset_id or "")
    if preset is not None:
        return list(preset.formulas)
    return list(DEFAULT_FORMULA_SETS.get(kind, []))


def competition_seed_ranks(seed_totals: dict[str, float]) -> dict[str, float]:
    """Seeding ranks with ties shared (1, 2, 2, 4) — the default ``seed_rank``."""
    return {
        team_id: float(rank) for team_id, rank in competition_ranks(seed_totals.items()).items()
    }


# Inputs the engine and the UI know about, with the label shown in the editor.
KNOWN_INPUTS: dict[str, str] = {
    "n": "Number of teams in the category (injected automatically)",
    "seed_runs": (
        "List of this team's seeding round scores (seeding phases only; "
        "a disqualified round is 0, negative scores count as 0)"
    ),
    "seed_rank": (
        "Seeding rank as displayed: equal seed scores share a rank unless the season "
        "applies tie-breakers to seeding"
    ),
    "de_rank": "Rank within the double-elimination bracket (0 = did not take part)",
    "de_score_recorded": "DE score as manually recorded, if one was entered",
    "n_bracket": "Number of teams in this team's bracket",
    "bracket_weight": "Weight of this team's bracket (announced per tournament)",
    "paper": "Paper score, 0-100",
    "doc_p1": "Period 1 documentation, rubric points",
    "doc_p2": "Period 2 documentation, rubric points",
    "doc_p3": "Period 3 documentation, rubric points",
    "onsite": "Onsite documentation, rubric points (not used at ECER)",
    "doc_p1_max": "Rubric maximum of Period 1 (2026: 100)",
    "doc_p2_max": "Rubric maximum of Period 2 (2026: 95)",
    "doc_p3_max": "Rubric maximum of Period 3 (2026: 100)",
    "onsite_max": "Rubric maximum of the onsite documentation (2026: 100)",
    "aerial_runs": "List of this team's aerial run scores",
    "aerial_counted_runs": "How many of the best aerial runs count (0 = all), per category",
    "jbc_points": "Junior Botball Challenge: points for solved challenges",
    "double_seed_runs": "List of double-seeding run scores (GCER only)",
    "double_seed_total": "Mean of all double-seeding runs, none dropped (GCER only)",
}
