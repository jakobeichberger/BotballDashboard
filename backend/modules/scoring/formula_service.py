"""Applies the stored formula sets to a season's actual results."""

from __future__ import annotations

from collections import Counter
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.exceptions import BadRequestError, NotFoundError
from modules.events.models import Event, EventRegistration
from modules.paper_review.models import Paper
from modules.scoring.competition_models import AerialResult, DEResult, DocumentationScore
from modules.scoring.formula import FormulaError, parse_formula, resolve_order
from modules.scoring.formula_engine import (
    DEFAULT_FORMULA_SETS,
    FORMULA_PRESETS,
    KNOWN_INPUTS,
    FormulaRunResult,
    run_formula_set,
)
from modules.scoring.formula_models import ScoringBracketWeight, ScoringFormula
from modules.scoring.models import Match
from modules.scoring.ranking import rank_descending
from modules.scoring.service import (
    DEFAULT_CATEGORY,
    DOUBLE_SEEDING,
    SEEDING,
    official_run_score,
    red_carded_teams,
    select_matches_with_kind,
    team_categories,
)
from modules.seasons.lifecycle import ensure_writable
from modules.teams.models import Team

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
    await ensure_writable(db, season_id=season_id)

    pairs = [(f["key"], f["expression"]) for f in formulas]
    keys = [k for k, _ in pairs]
    duplicates = [k for k, count in Counter(keys).items() if count > 1]
    if duplicates:
        raise BadRequestError(f"Duplicate formula key: {duplicates[0]}")

    validate_formula_set(pairs, formula_input_names())

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


async def apply_preset(
    db: AsyncSession, season_id: str, preset_id: str, category: str | None = None
) -> list[ScoringFormula]:
    """Replace a category's formulas with one of the shipped presets.

    `category` defaults to the preset's own; passing another one lets e.g. the
    GCER set be used for a differently named category.
    """
    preset = FORMULA_PRESETS.get(preset_id)
    if preset is None:
        raise NotFoundError(f"Unknown formula preset '{preset_id}'")
    return await replace_formula_set(
        db,
        season_id,
        category or preset.category,
        [{"key": k, "expression": e, "sort_order": i} for i, (k, e) in enumerate(preset.formulas)],
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
    await ensure_writable(db, season_id=season_id)
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


async def _season_of(db: AsyncSession, event_id: str) -> str:
    result = await db.execute(select(Event.season_id).where(Event.id == event_id))
    season_id = result.scalar_one_or_none()
    if not season_id:
        raise NotFoundError("Event not found")
    return season_id


def formula_input_names() -> set[str]:
    """Variables a formula may reference.

    The documented vocabulary only — deliberately not derived from the rows
    currently in the database, so a season can be configured before any team
    has registered or any result exists.
    """
    return set(KNOWN_INPUTS) | {"n", "team_id", "team_name", "category", "de_bracket"}


async def _event_participants(db: AsyncSession, event: Event) -> dict[str, str]:
    """team_id -> category for every team taking part in this event.

    The field is the event's own registrations plus any team that actually has
    a result here (match, DE, aerial or documentation) — not the season
    registration: a team registered for the season that never showed up at
    this event must not count towards n, or it shifts every seeding score.
    """
    registered = await db.execute(
        select(EventRegistration.team_id).where(EventRegistration.event_id == event.id)
    )
    team_ids: set[str] = set(registered.scalars().all())
    result_queries = (
        select(Match.team_id).where(Match.event_id == event.id, Match.is_practice.is_(False)),
        select(DEResult.team_id).where(DEResult.event_id == event.id),
        select(AerialResult.team_id).where(AerialResult.event_id == event.id),
        select(DocumentationScore.team_id).where(DocumentationScore.event_id == event.id),
    )
    for query in result_queries:
        team_ids.update((await db.execute(query.distinct())).scalars().all())
    categories = await team_categories(db, event, team_ids)
    return {t: categories.get(t, DEFAULT_CATEGORY) for t in team_ids}


async def build_inputs(db: AsyncSession, event_id: str, category: str) -> list[dict[str, Any]]:
    """Collect one input row per team taking part in `category` at this event.

    Results (matches, DE, aerial, documentation) are scoped to the event, and
    so is the field of teams (see _event_participants); the category comes
    from the event registration, falling back to the season registration.

    Seeding inputs follow the game review: only matches of seeding phases feed
    `seed_runs` (DE, alliance and final matches never do), a disqualified round
    counts as 0 instead of being dropped, and negative scores count as 0.
    Double-seeding matches feed `double_seed_runs`; `double_seed_total` is the
    mean of all of them, since double seeding drops no run.

    Every row carries `disqualified` (a red card anywhere at the event); the
    ranking takes those teams out of the field.

    Every key is always present (missing results become 0 / an empty list), so
    a formula never has to guard against a team that skipped a discipline.
    """
    event_row = await db.get(Event, event_id)
    if not event_row:
        raise NotFoundError("Event not found")
    season_id = event_row.season_id

    participants = await _event_participants(db, event_row)
    team_ids = {t for t, c in participants.items() if c == category}
    if not team_ids:
        return []
    names_result = await db.execute(select(Team.id, Team.name).where(Team.id.in_(team_ids)))
    names = dict(names_result.all())
    teams: list[dict[str, Any]] = sorted(
        (
            {"team_id": t, "team_name": names.get(t), "category": category}
            for t in team_ids
            if t in names
        ),
        key=lambda t: t["team_name"] or "",
    )

    seed_runs: dict[str, list[float]] = {t: [] for t in team_ids}
    double_seed_runs: dict[str, list[float]] = {t: [] for t in team_ids}
    matches = await db.execute(
        select_matches_with_kind(
            Match.team_id, Match.total_score, Match.is_disqualified, Match.round_lost
        )
        .where(
            Match.event_id == event_id,
            Match.team_id.in_(team_ids),
            # practice runs are preparation and never count toward the ranking
            Match.is_practice.is_(False),
        )
        .order_by(Match.round_number, Match.created_at)
    )
    # total_score already carries the end-contact bonus and is 0 for a lost
    # round; official_run_score applies the DQ / lost-round = 0 rule on top.
    for team_id, total, disqualified, round_lost, kind in matches.all():
        if kind == SEEDING:
            seed_runs[team_id].append(official_run_score(total, disqualified, round_lost))
        elif kind == DOUBLE_SEEDING:
            double_seed_runs[team_id].append(official_run_score(total, disqualified, round_lost))
    red_carded = await red_carded_teams(db, event_id)

    de_by_team: dict[str, DEResult] = {}
    de_rows = await db.execute(select(DEResult).where(DEResult.event_id == event_id))
    for d in de_rows.scalars():
        if d.team_id in team_ids:
            de_by_team[d.team_id] = d
    bracket_sizes = Counter(d.bracket for d in de_by_team.values() if d.bracket)
    # Per-event weights (announced per tournament) win over the season default.
    from modules.events.service import get_bracket_weights as event_bracket_weights

    weights = await event_bracket_weights(db, event_id, category)

    aerial_by_team: dict[str, AerialResult] = {}
    aerial_rows = await db.execute(select(AerialResult).where(AerialResult.event_id == event_id))
    for a in aerial_rows.scalars():
        if a.team_id in team_ids:
            aerial_by_team[a.team_id] = a

    doc_by_team: dict[str, DocumentationScore] = {}
    doc_rows = await db.execute(
        select(DocumentationScore).where(DocumentationScore.event_id == event_id)
    )
    for doc_row in doc_rows.scalars():
        if doc_row.team_id in team_ids:
            doc_by_team[doc_row.team_id] = doc_row

    # Papers are submitted and judged per season, not per event. final_score is
    # stored 0-1 (finalize_paper, PaperScoreUpdate); the formula input "paper"
    # is documented as 0-100 like the documentation inputs, so rescale here.
    paper_by_team: dict[str, float] = {}
    paper_rows = await db.execute(
        select(Paper).where(Paper.season_id == season_id, Paper.final_score.isnot(None))
    )
    for p in paper_rows.scalars():
        if p.team_id in team_ids:
            paper_by_team[p.team_id] = float(p.final_score or 0.0) * 100.0

    rows: list[dict[str, Any]] = []
    for t in teams:
        tid = t["team_id"]
        de = de_by_team.get(tid)
        aerial = aerial_by_team.get(tid)
        doc = doc_by_team.get(tid)
        bracket = de.bracket if de and de.bracket else ""
        double_runs = double_seed_runs.get(tid, [])
        rows.append(
            {
                **t,
                "disqualified": tid in red_carded,
                "seed_runs": seed_runs.get(tid, []),
                "double_seed_runs": double_runs,
                "double_seed_total": sum(double_runs) / len(double_runs) if double_runs else 0.0,
                "de_rank": float(de.de_rank) if de and de.de_rank else 0.0,
                # The de_score column as recorded by an admin. The default
                # formula derives DE from the rank as the game document does,
                # but a season can opt to use this value instead.
                "de_score_recorded": float(de.de_score) if de and de.de_score else 0.0,
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
    """Sort by `key` descending and assign competition ranks (ties share).

    Single pass over the sorted list rather than counting better rows for each
    row, so this stays O(n log n) on a large field.
    """
    ranked = rank_descending(rows, lambda r: r.get(key) or 0.0)
    for rank, row in ranked:
        row["rank"] = rank
    return [row for _, row in ranked]


def _run_and_rank(
    formulas: list[tuple[str, str]], rows: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], FormulaRunResult]:
    """Run the formulas over the eligible field and rank it.

    Red-carded teams are disqualified from the whole competition ranking: they
    are taken out of the field before the formulas run (so they count neither
    towards n nor towards any maximum) and are appended unranked, flagged
    `disqualified`, so the scoreboard can still show them.
    """
    eligible = [r for r in rows if not r.get("disqualified")]
    excluded = [{**r, "rank": None} for r in rows if r.get("disqualified")]
    run = run_formula_set(formulas, eligible) if eligible else FormulaRunResult()
    run.rows = _rank_rows(run.rows) + excluded
    return run.rows, run


async def compute_category_ranking(
    db: AsyncSession, event_id: str, category: str
) -> tuple[list[dict[str, Any]], FormulaRunResult]:
    """Rank one category at one event.

    Results come from the event; the formula set comes from the season the
    event belongs to, since the rules are published per season.
    """
    rows = await build_inputs(db, event_id, category)
    season_id = await _season_of(db, event_id)
    formulas = await get_formula_set(db, season_id, category)
    if not rows or not formulas:
        return [], FormulaRunResult(rows=rows)
    return _run_and_rank(formulas, rows)


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
        "double_seed_runs",
        "aerial_runs",
        "de_bracket",
        "disqualified",
    }
)


def to_ranking_entry(row: dict[str, Any]) -> dict[str, Any]:
    """Shape one computed row for the ranking API."""
    rank = row.get("rank")
    entry: dict[str, Any] = {
        "rank": int(rank) if rank is not None else None,
        "disqualified": bool(row.get("disqualified")),
        "team_id": row["team_id"],
        "team_name": row.get("team_name"),
        "category": row.get("category", ""),
    }
    for field, key in _ENTRY_FIELDS.items():
        value = row.get(key)
        entry[field] = (
            float(value) if isinstance(value, int | float) and not isinstance(value, bool) else None
        )
    entry["overall_score"] = entry["overall_score"] or 0.0
    entry["values"] = {
        k: float(v)
        for k, v in row.items()
        if k not in _INPUT_KEYS and isinstance(v, int | float) and not isinstance(v, bool)
    }
    return entry


async def compute_overall_ranking(
    db: AsyncSession, event_id: str, categories: list[str] | None = None
) -> list[dict[str, Any]]:
    """Formula-driven replacement for the old hard-coded overall ranking."""
    out: list[dict[str, Any]] = []
    for category in categories or CATEGORIES:
        ranked, _ = await compute_category_ranking(db, event_id, category)
        out.extend(to_ranking_entry(r) for r in ranked)
    return out


async def preview_formula_set(
    db: AsyncSession, event_id: str, category: str, formulas: list[tuple[str, str]]
) -> FormulaRunResult:
    """Run a candidate formula set against the event's real data without saving."""
    rows = await build_inputs(db, event_id, category)
    if not rows:
        return FormulaRunResult()
    _, run = _run_and_rank(formulas, rows)
    return run
