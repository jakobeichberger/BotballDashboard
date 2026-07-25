"""Applies the stored formula sets to a season's actual results."""

from __future__ import annotations

from collections import Counter
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.exceptions import BadRequestError, NotFoundError
from modules.paper_review.models import Paper
from modules.scoring.competition_models import AerialResult, DEResult, DocumentationScore
from modules.scoring.formula import FormulaError, parse_formula, resolve_order
from modules.scoring.formula_engine import (
    DEFAULT_FORMULA_SETS,
    KNOWN_INPUTS,
    FormulaRunResult,
    run_formula_set,
)
from modules.scoring.formula_models import ScoringBracketWeight, ScoringFormula
from modules.scoring.models import Match
from modules.teams.models import Team, TeamSeasonRegistration

CATEGORIES = ("botball", "open", "aerial", "jbc")


# ── Formula CRUD ──────────────────────────────────────────────────────────────


async def list_formulas(
    db: AsyncSession, season_id: str, category: str | None = None
) -> list[ScoringFormula]:
    q = select(ScoringFormula).where(ScoringFormula.season_id == season_id)
    if category:
        q = q.where(ScoringFormula.category == category)
    result = await db.execute(q.order_by(ScoringFormula.category, ScoringFormula.sort_order))
    return list(result.scalars().all())


async def get_formula_set(db: AsyncSession, season_id: str, category: str) -> list[tuple[str, str]]:
    """The (key, expression) pairs for a category.

    Falls back to the documented defaults when a season has not been
    customised, so a fresh season scores correctly without any setup.
    """
    rows = await list_formulas(db, season_id, category)
    active = [r for r in rows if r.is_active]
    if active:
        return [(r.key, r.expression) for r in active]
    return list(DEFAULT_FORMULA_SETS.get(category, []))


def validate_formula_set(formulas: list[tuple[str, str]], inputs: set[str]) -> None:
    """Raise BadRequestError if the set does not parse or cannot be ordered."""
    parsed = []
    for key, expression in formulas:
        try:
            parsed.append(parse_formula(key, expression))
        except FormulaError as exc:
            raise BadRequestError(f"{key}: {exc}") from exc
    try:
        # Only the real inputs are "already available" — passing the formula
        # keys in here too would mark every formula as satisfied and hide
        # cycles between them.
        resolve_order(parsed, inputs)
    except FormulaError as exc:
        raise BadRequestError(str(exc)) from exc


async def replace_formula_set(
    db: AsyncSession, season_id: str, category: str, formulas: list[dict[str, Any]]
) -> list[ScoringFormula]:
    """Replace every formula of one category in one transaction.

    Validated as a set before anything is written, so a broken formula cannot
    leave a season half-configured.
    """
    if category not in CATEGORIES:
        raise BadRequestError(f"Unknown category '{category}'")

    pairs = [(f["key"], f["expression"]) for f in formulas]
    keys = [k for k, _ in pairs]
    duplicates = [k for k, count in Counter(keys).items() if count > 1]
    if duplicates:
        raise BadRequestError(f"Duplicate formula key: {duplicates[0]}")

    validate_formula_set(pairs, await _input_names(db, season_id, category))

    await db.execute(
        delete(ScoringFormula).where(
            ScoringFormula.season_id == season_id, ScoringFormula.category == category
        )
    )
    created = [
        ScoringFormula(
            season_id=season_id,
            category=category,
            key=f["key"],
            expression=f["expression"],
            label=f.get("label"),
            description=f.get("description"),
            sort_order=f.get("sort_order", i),
            is_active=f.get("is_active", True),
        )
        for i, f in enumerate(formulas)
    ]
    db.add_all(created)
    await db.flush()
    return created


async def reset_to_defaults(
    db: AsyncSession, season_id: str, category: str
) -> list[ScoringFormula]:
    defaults = DEFAULT_FORMULA_SETS.get(category)
    if defaults is None:
        raise NotFoundError(f"No default formula set for category '{category}'")
    return await replace_formula_set(
        db,
        season_id,
        category,
        [{"key": k, "expression": e, "sort_order": i} for i, (k, e) in enumerate(defaults)],
    )


# ── Bracket weights ───────────────────────────────────────────────────────────


async def get_bracket_weights(db: AsyncSession, season_id: str, category: str) -> dict[str, float]:
    result = await db.execute(
        select(ScoringBracketWeight).where(
            ScoringBracketWeight.season_id == season_id,
            ScoringBracketWeight.category == category,
        )
    )
    return {r.bracket: r.weight for r in result.scalars()}


async def set_bracket_weights(
    db: AsyncSession, season_id: str, category: str, weights: dict[str, float]
) -> dict[str, float]:
    await db.execute(
        delete(ScoringBracketWeight).where(
            ScoringBracketWeight.season_id == season_id,
            ScoringBracketWeight.category == category,
        )
    )
    db.add_all(
        ScoringBracketWeight(
            season_id=season_id, category=category, bracket=bracket, weight=float(weight)
        )
        for bracket, weight in weights.items()
    )
    await db.flush()
    return weights


# ── Input gathering ───────────────────────────────────────────────────────────


async def _input_names(db: AsyncSession, season_id: str, category: str) -> set[str]:
    """Variables a formula may reference.

    Always includes the documented vocabulary, so a season can be configured
    before any team has registered — validating against the current rows alone
    would reject `seed_runs` on an empty season.
    """
    names = set(KNOWN_INPUTS) | {"n", "team_id", "team_name", "category", "de_bracket"}
    for r in await build_inputs(db, season_id, category):
        names.update(r)
    return names


async def build_inputs(db: AsyncSession, season_id: str, category: str) -> list[dict[str, Any]]:
    """Collect one input row per team registered in `category`.

    Every key is always present (missing results become 0 / an empty list), so
    a formula never has to guard against a team that skipped a discipline.
    """
    teams_result = await db.execute(
        select(Team.id, Team.name, TeamSeasonRegistration.category)
        .join(TeamSeasonRegistration, TeamSeasonRegistration.team_id == Team.id)
        .where(
            TeamSeasonRegistration.season_id == season_id,
            TeamSeasonRegistration.category == category,
        )
        .order_by(Team.name)
    )
    teams = [{"team_id": r.id, "team_name": r.name, "category": r.category} for r in teams_result]
    if not teams:
        return []
    team_ids = {t["team_id"] for t in teams}

    seed_runs: dict[str, list[float]] = {t: [] for t in team_ids}
    matches = await db.execute(
        select(Match)
        .where(Match.season_id == season_id, Match.is_disqualified.is_(False))
        .order_by(Match.round_number)
    )
    for m in matches.scalars():
        if m.team_id in seed_runs:
            seed_runs[m.team_id].append(float(m.total_score or 0.0))

    de_by_team: dict[str, DEResult] = {}
    de_rows = await db.execute(select(DEResult).where(DEResult.season_id == season_id))
    for d in de_rows.scalars():
        if d.team_id in team_ids:
            de_by_team[d.team_id] = d
    bracket_sizes = Counter(d.bracket for d in de_by_team.values() if d.bracket)
    weights = await get_bracket_weights(db, season_id, category)

    aerial_by_team: dict[str, AerialResult] = {}
    aerial_rows = await db.execute(select(AerialResult).where(AerialResult.season_id == season_id))
    for a in aerial_rows.scalars():
        if a.team_id in team_ids:
            aerial_by_team[a.team_id] = a

    doc_by_team: dict[str, DocumentationScore] = {}
    doc_rows = await db.execute(
        select(DocumentationScore).where(DocumentationScore.season_id == season_id)
    )
    for d in doc_rows.scalars():
        if d.team_id in team_ids:
            doc_by_team[d.team_id] = d

    paper_by_team: dict[str, float] = {}
    paper_rows = await db.execute(
        select(Paper).where(Paper.season_id == season_id, Paper.final_score.isnot(None))
    )
    for p in paper_rows.scalars():
        if p.team_id in team_ids:
            paper_by_team[p.team_id] = float(p.final_score or 0.0)

    rows: list[dict[str, Any]] = []
    for t in teams:
        tid = t["team_id"]
        de = de_by_team.get(tid)
        aerial = aerial_by_team.get(tid)
        doc = doc_by_team.get(tid)
        bracket = de.bracket if de and de.bracket else ""
        rows.append(
            {
                **t,
                "seed_runs": seed_runs.get(tid, []),
                "de_rank": float(de.de_rank) if de and de.de_rank else 0.0,
                "de_bracket": bracket,
                "n_bracket": float(bracket_sizes.get(bracket, 0)),
                "bracket_weight": float(weights.get(bracket, 1.0)),
                "aerial_runs": [
                    float(v)
                    for v in (
                        (aerial.run1, aerial.run2, aerial.run3, aerial.run4) if aerial else ()
                    )
                    if v is not None
                ],
                "doc_p1": float(doc.part1) if doc and doc.part1 is not None else 0.0,
                "doc_p2": float(doc.part2) if doc and doc.part2 is not None else 0.0,
                "doc_p3": float(doc.part3) if doc and doc.part3 is not None else 0.0,
                "onsite": float(doc.onsite) if doc and doc.onsite is not None else 0.0,
                "paper": paper_by_team.get(tid, 0.0),
            }
        )
    return rows


# ── Ranking ───────────────────────────────────────────────────────────────────


def _rank_rows(rows: list[dict[str, Any]], key: str = "overall") -> list[dict[str, Any]]:
    """Sort by `key` descending and assign competition ranks (ties share)."""
    ordered = sorted(rows, key=lambda r: r.get(key) or 0.0, reverse=True)
    for row in ordered:
        value = row.get(key) or 0.0
        row["rank"] = 1 + sum(1 for o in ordered if (o.get(key) or 0.0) > value)
    return ordered


async def compute_category_ranking(
    db: AsyncSession, season_id: str, category: str
) -> tuple[list[dict[str, Any]], FormulaRunResult]:
    rows = await build_inputs(db, season_id, category)
    formulas = await get_formula_set(db, season_id, category)
    if not rows or not formulas:
        return [], FormulaRunResult(rows=rows)
    run = run_formula_set(formulas, rows)
    return _rank_rows(run.rows), run


#: Formula keys that have a dedicated field on OverallRankingEntry.
_ENTRY_FIELDS = {
    "overall_score": "overall",
    "seeding_score": "seed_score",
    "de_score": "de_score",
    "paper_score": "paper_score",
    "doc_score": "doc_score",
    "aerial_score": "aerial_score",
}

#: Inputs that are echoed back rather than reported as computed values.
_INPUT_KEYS = frozenset(
    {
        "team_id",
        "team_name",
        "category",
        "rank",
        "n",
        "seed_runs",
        "aerial_runs",
        "de_bracket",
    }
)


def to_ranking_entry(row: dict[str, Any]) -> dict[str, Any]:
    """Shape one computed row for the ranking API."""
    entry: dict[str, Any] = {
        "rank": int(row.get("rank") or 0),
        "team_id": row["team_id"],
        "team_name": row.get("team_name"),
        "category": row.get("category", ""),
    }
    for field, key in _ENTRY_FIELDS.items():
        value = row.get(key)
        entry[field] = float(value) if isinstance(value, int | float) else None
    entry["overall_score"] = entry["overall_score"] or 0.0
    entry["values"] = {
        k: float(v)
        for k, v in row.items()
        if k not in _INPUT_KEYS and isinstance(v, int | float) and not isinstance(v, bool)
    }
    return entry


async def compute_overall_ranking(
    db: AsyncSession, season_id: str, categories: list[str] | None = None
) -> list[dict[str, Any]]:
    """Formula-driven replacement for the old hard-coded overall ranking."""
    out: list[dict[str, Any]] = []
    for category in categories or CATEGORIES:
        ranked, _ = await compute_category_ranking(db, season_id, category)
        out.extend(to_ranking_entry(r) for r in ranked)
    return out


async def preview_formula_set(
    db: AsyncSession, season_id: str, category: str, formulas: list[tuple[str, str]]
) -> FormulaRunResult:
    """Run a candidate formula set against the season's real data without saving."""
    rows = await build_inputs(db, season_id, category)
    if not rows:
        return FormulaRunResult()
    run = run_formula_set(formulas, rows)
    run.rows = _rank_rows(run.rows)
    return run
