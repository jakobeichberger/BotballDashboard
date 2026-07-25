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
    evaluate,
    parse_formula,
    resolve_order,
)


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

    for p in ordered:
        computed: list[float] = []
        for row in working:
            try:
                value = evaluate(p, row, columns)
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
# Sources:
#   * "Botball Game Review" (2025 v1.2 / 2026 v1.3), section
#     "Overall Winner Calculations":
#         SeedScore = 3/4·((n − SeedRank + 1)/n)
#                   + 1/4·(TeamAverageSeedScore / MaxTournamentSeedScore)
#         DoubleEliminationScore = (n − DERank + 1)/n
#         DocScore  = 2/10·P1% + 2/10·P2% + 2/10·P3% + 4/10·Onsite%
#         Overall   = Seeding + DE + Documentation
#   * "ECER Amendments" (2025 v1.1): no Onsite at ECER, so the three period
#     documentations are rescaled to sum to 1, and the paper halves the weight
#     of the documentation score:
#         DocScore         = 1/3·P1 + 1/3·P2 + 1/3·P3
#         AdaptedDocScore  = 1/2·DocScore + 1/2·PaperScore
#         Overall (Botball)= DE + Seeding + AdaptedDocScore
#         Overall (Open)   = DE + Seeding + 1/2·PaperScore
#   * "Note #2: Weighting of brackets ... will be released at GCER" — hence
#     bracket_weight is an input, not a constant. ECER 2025 used 1.0 for
#     bracket A and ~0.5684 for bracket B.

_SEED_TOTAL = ("seed_total", "avg_best(seed_runs, 2)")
_SEED_SCORE = (
    "seed_score",
    "3/4 * ((n - rank(seed_total) + 1) / n) + 1/4 * safe_div(seed_total, max_all(seed_runs))",
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
    # PRIA Open: same seeding and DE, no Botball documentation.
    "open": [
        _SEED_TOTAL,
        _SEED_SCORE,
        _DE_BRACKET_SCORE,
        _DE_SCORE,
        _PAPER_SCORE,
        ("overall", "seed_score + de_score + 0.5 * paper_score"),
    ],
    # Aerial: ECER 2025 ranked on the mean of all four runs.
    "aerial": [
        ("aerial_score", "avg(aerial_runs)"),
        ("overall", "aerial_score"),
    ],
    # Junior Botball Challenge: seeding only.
    "jbc": [
        _SEED_TOTAL,
        _SEED_SCORE,
        ("overall", "seed_score"),
    ],
}

# GCER runs the full documentation formula including the onsite presentation,
# and adds a double-seeding score, so the overall score there is 0..4.
GCER_BOTBALL_FORMULA_SET: list[tuple[str, str]] = [
    _SEED_TOTAL,
    _SEED_SCORE,
    _DE_BRACKET_SCORE,
    _DE_SCORE,
    (
        "doc_score",
        "0.2 * (doc_p1/100) + 0.2 * (doc_p2/100) + 0.2 * (doc_p3/100) + 0.4 * (onsite/100)",
    ),
    _PAPER_SCORE,
    (
        "double_seed_score",
        "2/3 * ((n - rank(double_seed_total) + 1) / n)"
        " + 1/3 * safe_div(double_seed_total, max_all(double_seed_runs))",
    ),
    ("overall", "seed_score + de_score + doc_score + double_seed_score"),
]


# Inputs the engine and the UI know about, with the label shown in the editor.
KNOWN_INPUTS: dict[str, str] = {
    "n": "Number of teams in the category (injected automatically)",
    "seed_runs": "List of this team's seeding run scores",
    "seed_rank": "Seeding rank, if entered manually instead of computed",
    "de_rank": "Rank within the double-elimination bracket (0 = did not take part)",
    "n_bracket": "Number of teams in this team's bracket",
    "bracket_weight": "Weight of this team's bracket (announced per tournament)",
    "paper": "Paper score, 0-100",
    "doc_p1": "Period 1 documentation, 0-100",
    "doc_p2": "Period 2 documentation, 0-100",
    "doc_p3": "Period 3 documentation, 0-100",
    "onsite": "Onsite documentation, 0-100 (not used at ECER)",
    "aerial_runs": "List of this team's aerial run scores",
    "double_seed_runs": "List of double-seeding run scores (GCER only)",
    "double_seed_total": "Double-seeding total (GCER only)",
}
