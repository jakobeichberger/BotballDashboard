"""
Service logic for DE, aerial and documentation results.

Every function works on one event: results are recorded per event, and a
season with an ECER and a GCER must keep them apart. The stored score columns
(`bracket_score`, aerial `score`, `doc_score`, JBC `rank`) are what the team's
category formula set computes (``sync_event_scores``), so the result tables
agree with the overall ranking computed by formula_service. Where a formula
set has no such column, the game-review rule applies.

Each change is recorded in ResultRevision, so a corrected result stays
traceable like a corrected match score.
"""

from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.exceptions import ValidationError
from modules.events.models import Event
from modules.scoring import rules_service
from modules.scoring.competition_models import (
    AerialResult,
    DEResult,
    DocumentationScore,
    JBCResult,
    ResultRevision,
)
from modules.scoring.ranking import competition_ranks
from modules.scoring.service import DEFAULT_CATEGORY, team_categories
from modules.seasons.lifecycle import ensure_writable
from modules.teams.models import Team

_DE_FIELDS = ("bracket", "de_rank", "bracket_score", "de_score", "notes")
_AERIAL_FIELDS = ("runs", "score", "notes")
_DOC_FIELDS = ("part1", "part2", "part3", "onsite", "doc_score", "notes")
_JBC_FIELDS = ("points", "challenges", "notes")

#: Documentation weights of the 2025/2026 game review (regional tournaments).
DOC_WEIGHTS = (0.2, 0.2, 0.2, 0.4)
_DOC_PARTS = (("part1", "p1"), ("part2", "p2"), ("part3", "p3"), ("onsite", "onsite"))


def aerial_score(runs: list[float | None], counted: int | None = None) -> float | None:
    """Mean of the best ``counted`` runs, or of every recorded run.

    ECER 2025 ranked on all runs; the 2026 Aerial Junior rulebook on the best
    three. A team with fewer runs than ``counted`` is averaged over the runs
    it has (like avg_best in the formula engine).
    """
    valid = sorted((float(r) for r in runs if r is not None), reverse=True)
    if counted:
        valid = valid[:counted]
    return sum(valid) / len(valid) if valid else None


def documentation_score(
    part1: float | None,
    part2: float | None,
    part3: float | None,
    onsite: float | None,
    maxima: dict[str, float] | None = None,
) -> float | None:
    """0.2·P1 + 0.2·P2 + 0.2·P3 + 0.4·Onsite, each relative to its rubric maximum.

    A missing part scores 0 — it is not left out of the average, which would
    reward a team for not handing a part in. None only when nothing is entered.
    """
    parts = (part1, part2, part3, onsite)
    if all(p is None for p in parts):
        return None
    limits = maxima or rules_service.DOC_MAX_DEFAULT
    return sum(
        w * (p or 0.0) / limits[key]
        for w, p, (_, key) in zip(DOC_WEIGHTS, parts, _DOC_PARTS, strict=True)
    )


def bracket_score(n_bracket: int, de_rank: int) -> float:
    """DoubleEliminationScore = (n − DERank + 1) / n."""
    return (n_bracket - de_rank + 1) / n_bracket if n_bracket else 0.0


def _snapshot(row: Any, fields: tuple[str, ...]) -> dict[str, Any]:
    return {f: getattr(row, f) for f in fields}


async def _refresh(db: AsyncSession, rows: list[Any]) -> None:
    """Reload server-maintained columns (updated_at) before the rows are serialised.

    One SELECT for all rows (populate_existing refreshes the loaded objects),
    not one refresh per row.
    """
    if not rows:
        return
    model = type(rows[0])
    await db.execute(
        select(model)
        .where(model.id.in_({row.id for row in rows}))
        .execution_options(populate_existing=True)
    )


#: Scores derived from the inputs (and, through the formula set, from the
#: other teams' results): a write that changes no input is not a revision.
_DERIVED = frozenset({"score", "doc_score"})


def _inputs(snapshot: dict[str, Any] | None) -> dict[str, Any] | None:
    if snapshot is None:
        return None
    return {k: v for k, v in snapshot.items() if k not in _DERIVED}


async def _record(
    db: AsyncSession,
    event: Event,
    team_id: str,
    kind: str,
    previous: dict[str, Any] | None,
    new: dict[str, Any] | None,
    changed_by: str | None,
) -> None:
    if _inputs(previous) == _inputs(new):
        return
    db.add(
        ResultRevision(
            event_id=event.id,
            team_id=team_id,
            kind=kind,
            previous_value=previous,
            new_value=new,
            changed_by=changed_by,
        )
    )


async def list_result_revisions(
    db: AsyncSession,
    event: Event,
    kind: str | None = None,
    team_id: str | None = None,
    limit: int = 500,
) -> list[ResultRevision]:
    query = select(ResultRevision).where(ResultRevision.event_id == event.id)
    if kind:
        query = query.where(ResultRevision.kind == kind)
    if team_id:
        query = query.where(ResultRevision.team_id == team_id)
    result = await db.execute(query.order_by(ResultRevision.created_at.desc()).limit(limit))
    return list(result.scalars().all())


async def _upsert(
    db: AsyncSession,
    model: Any,
    event: Event,
    entries: list[dict],
    fields: tuple[str, ...],
    kind: str,
    changed_by: str | None,
    derive: Any = None,
) -> list[Any]:
    """Insert or update one result row per entry (one per team and event).

    The existing rows are loaded with one query and written with one flush,
    so a bulk save costs about the same number of statements for 5 or 150
    teams.
    """
    # Results of an archived season/event are read-only history.
    await ensure_writable(db, event_id=event.id)
    team_ids = {entry["team_id"] for entry in entries}
    loaded = await db.execute(
        select(model).where(model.event_id == event.id, model.team_id.in_(team_ids))
    )
    found: list[Any] = list(loaded.scalars())
    existing: dict[str, Any] = {row.team_id: row for row in found}
    rows: list[Any] = []
    changes: list[tuple[str, dict[str, Any] | None, dict[str, Any]]] = []
    for entry in entries:
        data = dict(entry)
        team_id = data.pop("team_id")
        row = existing.get(team_id)
        previous = _snapshot(row, fields) if row is not None else None
        if row is None:
            row = model(season_id=event.season_id, event_id=event.id, team_id=team_id, **data)
            db.add(row)
            existing[team_id] = row
        else:
            for k, v in data.items():
                setattr(row, k, v)
        if derive:
            derive(row)
        changes.append((team_id, previous, _snapshot(row, fields)))
        rows.append(row)
    await db.flush()
    for team_id, previous, new in changes:
        await _record(db, event, team_id, kind, previous, new, changed_by)
    return rows


# ── Double Elimination ────────────────────────────────────────────────────────


async def get_de_results(db: AsyncSession, event: Event) -> list[DEResult]:
    result = await db.execute(select(DEResult).where(DEResult.event_id == event.id))
    return list(result.scalars())


async def rescore_brackets(db: AsyncSession, event: Event) -> None:
    """Derive every bracket_score of the event from the DE ranks.

    n is the number of teams in the bracket within the team's category — the
    same grouping the formula engine uses for `n_bracket`.
    """
    rows = await get_de_results(db, event)
    categories = await team_categories(db, event, [r.team_id for r in rows])
    sizes: dict[tuple[str, str], int] = defaultdict(int)
    for r in rows:
        sizes[(categories.get(r.team_id, DEFAULT_CATEGORY), r.bracket)] += 1
    for r in rows:
        if r.de_rank:
            n = sizes[(categories.get(r.team_id, DEFAULT_CATEGORY), r.bracket)]
            r.bracket_score = bracket_score(n, r.de_rank)
    await db.flush()


async def upsert_de_result(
    db: AsyncSession,
    event: Event,
    data: dict,
    changed_by: str | None = None,
    *,
    rescore: bool = True,
) -> DEResult:
    [row] = await _upsert(db, DEResult, event, [data], _DE_FIELDS, "de", changed_by)
    if rescore:
        await rescore_brackets(db, event)
        await _refresh(db, [row])
    return row


async def bulk_upsert_de_results(
    db: AsyncSession, event: Event, entries: list[dict], changed_by: str | None = None
) -> list[DEResult]:
    rows = await _upsert(db, DEResult, event, entries, _DE_FIELDS, "de", changed_by)
    await rescore_brackets(db, event)
    await _refresh(db, rows)
    return rows


# ── Aerial ────────────────────────────────────────────────────────────────────


async def get_aerial_results(db: AsyncSession, event: Event) -> list[AerialResult]:
    result = await db.execute(select(AerialResult).where(AerialResult.event_id == event.id))
    return list(result.scalars())


def _derive_aerial(row: AerialResult) -> None:
    # Provisional until sync_event_scores applies the category's rule.
    row.score = aerial_score(list(row.runs or []))


async def _rerank_aerial(db: AsyncSession, event: Event) -> None:
    await sync_event_scores(db, event.id, kinds=("aerial",))


async def upsert_aerial_result(
    db: AsyncSession,
    event: Event,
    data: dict,
    changed_by: str | None = None,
    *,
    rerank: bool = True,
) -> AerialResult:
    [row] = await _upsert(
        db, AerialResult, event, [data], _AERIAL_FIELDS, "aerial", changed_by, _derive_aerial
    )
    if rerank:
        await _rerank_aerial(db, event)
        await _refresh(db, [row])
    return row


async def bulk_upsert_aerial_results(
    db: AsyncSession, event: Event, entries: list[dict], changed_by: str | None = None
) -> list[AerialResult]:
    rows = await _upsert(
        db, AerialResult, event, entries, _AERIAL_FIELDS, "aerial", changed_by, _derive_aerial
    )
    await _rerank_aerial(db, event)
    await _refresh(db, rows)
    return rows


async def get_aerial_ranking(db: AsyncSession, event: Event) -> list[dict]:
    """Aerial ranking with team names; ties share a rank."""
    rows = [r for r in await get_aerial_results(db, event) if r.score is not None]
    names_result = await db.execute(
        select(Team.id, Team.name).where(Team.id.in_([r.team_id for r in rows]))
    )
    names = {team_id: name for team_id, name in names_result.all()}
    categories = await team_categories(db, event, [r.team_id for r in rows])
    rows.sort(
        key=lambda r: (
            categories.get(r.team_id, DEFAULT_CATEGORY),
            r.rank or 0,
            names.get(r.team_id) or "",
        )
    )
    return [
        {
            # Ranked within the team's category (Aerial Junior / Senior).
            "rank": r.rank,
            "team_id": r.team_id,
            "team_name": names.get(r.team_id),
            "category": categories.get(r.team_id, DEFAULT_CATEGORY),
            "runs": list(r.runs or []),
            "score": r.score,
        }
        for r in rows
    ]


# ── Documentation ─────────────────────────────────────────────────────────────


async def get_doc_scores(db: AsyncSession, event: Event) -> list[DocumentationScore]:
    result = await db.execute(
        select(DocumentationScore).where(DocumentationScore.event_id == event.id)
    )
    return list(result.scalars())


def _derive_doc(row: DocumentationScore) -> None:
    # Provisional until sync_event_scores applies the category's formula set.
    row.doc_score = documentation_score(row.part1, row.part2, row.part3, row.onsite)


async def _check_doc_maxima(db: AsyncSession, event: Event, entries: list[dict]) -> None:
    """Rubric points may not exceed the season's maximum of the period."""
    maxima = (await rules_service.get_rules(db, event.season_id)).doc_max_points
    for data in entries:
        for part, key in _DOC_PARTS:
            value = data.get(part)
            if value is not None and value > maxima[key]:
                raise ValidationError(f"{part} must be at most {maxima[key]:g}")


async def _rerank_docs(db: AsyncSession, event: Event) -> None:
    await sync_event_scores(db, event.id, kinds=("doc",))


async def upsert_doc_score(
    db: AsyncSession,
    event: Event,
    data: dict,
    changed_by: str | None = None,
    *,
    rerank: bool = True,
) -> DocumentationScore:
    await _check_doc_maxima(db, event, [data])
    [row] = await _upsert(
        db, DocumentationScore, event, [data], _DOC_FIELDS, "doc", changed_by, _derive_doc
    )
    if rerank:
        await _rerank_docs(db, event)
        await _refresh(db, [row])
    return row


async def bulk_upsert_doc_scores(
    db: AsyncSession, event: Event, entries: list[dict], changed_by: str | None = None
) -> list[DocumentationScore]:
    await _check_doc_maxima(db, event, entries)
    rows = await _upsert(
        db, DocumentationScore, event, entries, _DOC_FIELDS, "doc", changed_by, _derive_doc
    )
    await _rerank_docs(db, event)
    await _refresh(db, rows)
    return rows


# ── Junior Botball Challenge ──────────────────────────────────────────────────


async def get_jbc_results(db: AsyncSession, event: Event) -> list[JBCResult]:
    result = await db.execute(select(JBCResult).where(JBCResult.event_id == event.id))
    return list(result.scalars())


def _derive_jbc(row: JBCResult) -> None:
    """With a challenge list, the points are the sum of the solved challenges."""
    if row.challenges:
        row.points = float(sum(float(c.get("points") or 0) for c in row.challenges))


async def upsert_jbc_result(
    db: AsyncSession,
    event: Event,
    data: dict,
    changed_by: str | None = None,
    *,
    rerank: bool = True,
) -> JBCResult:
    [row] = await _upsert(db, JBCResult, event, [data], _JBC_FIELDS, "jbc", changed_by, _derive_jbc)
    if rerank:
        await sync_event_scores(db, event.id, kinds=("jbc",))
        await _refresh(db, [row])
    return row


async def bulk_upsert_jbc_results(
    db: AsyncSession, event: Event, entries: list[dict], changed_by: str | None = None
) -> list[JBCResult]:
    rows = await _upsert(db, JBCResult, event, entries, _JBC_FIELDS, "jbc", changed_by, _derive_jbc)
    await sync_event_scores(db, event.id, kinds=("jbc",))
    await _refresh(db, rows)
    return rows


# ── Stored scores follow the formula set ─────────────────────────────────────


def _ranks_per_category(
    rows: list[Any], categories: dict[str, str], value: Any
) -> dict[str, int | None]:
    """Competition rank of each row within its team's category."""
    grouped: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for row in rows:
        score = value(row)
        if score is not None:
            grouped[categories.get(row.team_id, DEFAULT_CATEGORY)].append((row.team_id, score))
    ranks: dict[str, int | None] = {}
    for pairs in grouped.values():
        ranks.update(competition_ranks(pairs))
    return ranks


async def sync_event_scores(
    db: AsyncSession, event_id: str, kinds: tuple[str, ...] = ("aerial", "doc", "jbc")
) -> None:
    """Write the aerial, documentation and JBC scores and ranks of an event.

    ``score`` / ``doc_score`` are the ``aerial_score`` / ``doc_score`` columns
    of the team's category formula set — ECER 2026 normalises every
    documentation period to the best team, which a single row cannot know.
    Where the set has no such column (or it failed for the team), the plain
    rule applies: the category's counted aerial runs, and the game-review
    documentation weighting of the season's rubric maxima. Ranks are
    competition ranks within the category.
    """
    from modules.scoring import formula_service

    data = await formula_service.load_event_inputs(db, event_id)
    computed: dict[str, dict[str, Any]] = {}
    failed: dict[str, set[str]] = {}
    for category in sorted(set(data.participants.values())):
        ranked, run = await formula_service.compute_category_ranking(
            db, event_id, category, data=data
        )
        broken = {issue.key for issue in run.issues}
        for row in ranked:
            computed[row["team_id"]] = row
            failed[row["team_id"]] = broken

    def formula_value(team_id: str, key: str) -> float | None:
        row = computed.get(team_id) or {}
        value = row.get(key)
        if key in failed.get(team_id, set()) or not isinstance(value, int | float):
            return None
        return float(value)

    categories = data.participants
    if "aerial" in kinds:
        aerial_rows = list(data.aerial_by_team.values())
        for aerial in aerial_rows:
            runs = [r for r in (aerial.runs or []) if r is not None]
            entry = data.categories.get(categories.get(aerial.team_id, DEFAULT_CATEGORY)) or {}
            value = formula_value(aerial.team_id, "aerial_score")
            aerial.score = (
                (value if value is not None else aerial_score(runs, entry.get("counted_runs")))
                if runs
                else None
            )
        ranks = _ranks_per_category(aerial_rows, categories, lambda r: r.score)
        for aerial in aerial_rows:
            aerial.rank = ranks.get(aerial.team_id)
    if "doc" in kinds:
        doc_rows = list(data.doc_by_team.values())
        for doc in doc_rows:
            parts = (doc.part1, doc.part2, doc.part3, doc.onsite)
            value = formula_value(doc.team_id, "doc_score")
            if all(p is None for p in parts):
                doc.doc_score = None
            elif value is not None:
                doc.doc_score = value
            else:
                doc.doc_score = documentation_score(*parts, maxima=data.doc_max)
        ranks = _ranks_per_category(doc_rows, categories, lambda r: r.doc_score)
        for doc in doc_rows:
            doc.doc_rank = ranks.get(doc.team_id)
    if "jbc" in kinds:
        jbc_rows = list(data.jbc_by_team.values())
        ranks = _ranks_per_category(jbc_rows, categories, lambda r: r.points)
        for jbc in jbc_rows:
            jbc.rank = ranks.get(jbc.team_id)
    await db.flush()


async def get_jbc_ranking(db: AsyncSession, event: Event) -> list[dict]:
    """JBC ranking with team names: points for solved challenges, ties share."""
    rows = [r for r in await get_jbc_results(db, event) if r.points is not None]
    names = dict(
        (
            await db.execute(
                select(Team.id, Team.name).where(Team.id.in_([r.team_id for r in rows]))
            )
        ).all()
    )
    rows.sort(key=lambda r: (r.rank or 0, names.get(r.team_id) or ""))
    return [
        {
            "rank": r.rank,
            "team_id": r.team_id,
            "team_name": names.get(r.team_id),
            "points": r.points,
            "challenges": list(r.challenges or []),
        }
        for r in rows
    ]
