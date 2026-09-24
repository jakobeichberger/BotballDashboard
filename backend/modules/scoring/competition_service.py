"""
Service logic for DE, aerial and documentation results.

Every function works on one event: results are recorded per event, and a
season with an ECER and a GCER must keep them apart. The stored score columns
(`bracket_score`, aerial `score`, `doc_score`) follow the game review so the
legacy displays agree with the formula engine; the overall ranking itself is
computed by formula_service.

Each change is recorded in ResultRevision, so a corrected result stays
traceable like a corrected match score.
"""

from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.events.models import Event
from modules.scoring.competition_models import (
    AerialResult,
    DEResult,
    DocumentationScore,
    ResultRevision,
)
from modules.scoring.service import DEFAULT_CATEGORY, competition_ranks, team_categories
from modules.seasons.lifecycle import ensure_writable
from modules.teams.models import Team

_DE_FIELDS = ("bracket", "de_rank", "bracket_score", "de_score", "notes")
_AERIAL_FIELDS = ("run1", "run2", "run3", "run4", "score", "notes")
_DOC_FIELDS = ("part1", "part2", "part3", "onsite", "doc_score", "notes")

#: Documentation weights of the 2025/2026 game review (regional tournaments).
DOC_WEIGHTS = (0.2, 0.2, 0.2, 0.4)


def aerial_score(runs: list[float | None]) -> float | None:
    """Mean of every recorded aerial run (ECER 2025 ranked on all runs)."""
    valid = [float(r) for r in runs if r is not None]
    return sum(valid) / len(valid) if valid else None


def documentation_score(
    part1: float | None, part2: float | None, part3: float | None, onsite: float | None
) -> float | None:
    """0.2·P1 + 0.2·P2 + 0.2·P3 + 0.4·Onsite, each 0-100, result 0-1.

    A missing part scores 0 — it is not left out of the average, which would
    reward a team for not handing a part in. None only when nothing is entered.
    """
    parts = (part1, part2, part3, onsite)
    if all(p is None for p in parts):
        return None
    return sum(w * (p or 0.0) / 100.0 for w, p in zip(DOC_WEIGHTS, parts, strict=True))


def bracket_score(n_bracket: int, de_rank: int) -> float:
    """DoubleEliminationScore = (n − DERank + 1) / n."""
    return (n_bracket - de_rank + 1) / n_bracket if n_bracket else 0.0


def _snapshot(row: Any, fields: tuple[str, ...]) -> dict[str, Any]:
    return {f: getattr(row, f) for f in fields}


async def _refresh(db: AsyncSession, rows: list[Any]) -> None:
    """Reload server-maintained columns (updated_at) before the rows are serialised."""
    for row in rows:
        await db.refresh(row)


async def _record(
    db: AsyncSession,
    event: Event,
    team_id: str,
    kind: str,
    previous: dict[str, Any] | None,
    new: dict[str, Any] | None,
    changed_by: str | None,
) -> None:
    if previous == new:
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
    data: dict,
    fields: tuple[str, ...],
    kind: str,
    changed_by: str | None,
    derive: Any = None,
) -> Any:
    # Results of an archived season/event are read-only history.
    await ensure_writable(db, event_id=event.id)
    data = dict(data)
    team_id = data.pop("team_id")
    existing = await db.execute(
        select(model).where(model.event_id == event.id, model.team_id == team_id)
    )
    row = existing.scalar_one_or_none()
    previous = _snapshot(row, fields) if row is not None else None
    if row is None:
        row = model(season_id=event.season_id, event_id=event.id, team_id=team_id, **data)
        db.add(row)
    else:
        for k, v in data.items():
            setattr(row, k, v)
    if derive:
        derive(row)
    await db.flush()
    await _record(db, event, team_id, kind, previous, _snapshot(row, fields), changed_by)
    return row


# ── Double Elimination ────────────────────────────────────────────────────────


async def get_de_results(db: AsyncSession, event: Event) -> list[DEResult]:
    result = await db.execute(select(DEResult).where(DEResult.event_id == event.id))
    return list(result.scalars())


async def _rescore_brackets(db: AsyncSession, event: Event) -> None:
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
    row = await _upsert(db, DEResult, event, data, _DE_FIELDS, "de", changed_by)
    if rescore:
        await _rescore_brackets(db, event)
        await _refresh(db, [row])
    return row


async def bulk_upsert_de_results(
    db: AsyncSession, event: Event, entries: list[dict], changed_by: str | None = None
) -> list[DEResult]:
    rows = [await upsert_de_result(db, event, e, changed_by, rescore=False) for e in entries]
    await _rescore_brackets(db, event)
    await _refresh(db, rows)
    return rows


# ── Aerial ────────────────────────────────────────────────────────────────────


async def get_aerial_results(db: AsyncSession, event: Event) -> list[AerialResult]:
    result = await db.execute(select(AerialResult).where(AerialResult.event_id == event.id))
    return list(result.scalars())


def _derive_aerial(row: AerialResult) -> None:
    row.score = aerial_score([row.run1, row.run2, row.run3, row.run4])


async def _rerank_aerial(db: AsyncSession, event: Event) -> None:
    rows = await get_aerial_results(db, event)
    ranks = competition_ranks([(r.team_id, r.score) for r in rows if r.score is not None])
    for r in rows:
        r.rank = ranks.get(r.team_id)
    await db.flush()


async def upsert_aerial_result(
    db: AsyncSession,
    event: Event,
    data: dict,
    changed_by: str | None = None,
    *,
    rerank: bool = True,
) -> AerialResult:
    row = await _upsert(
        db, AerialResult, event, data, _AERIAL_FIELDS, "aerial", changed_by, _derive_aerial
    )
    if rerank:
        await _rerank_aerial(db, event)
        await _refresh(db, [row])
    return row


async def bulk_upsert_aerial_results(
    db: AsyncSession, event: Event, entries: list[dict], changed_by: str | None = None
) -> list[AerialResult]:
    rows = [await upsert_aerial_result(db, event, e, changed_by, rerank=False) for e in entries]
    await _rerank_aerial(db, event)
    await _refresh(db, rows)
    return rows


async def get_aerial_ranking(db: AsyncSession, event: Event) -> list[dict]:
    """Aerial ranking with team names; ties share a rank."""
    rows = [r for r in await get_aerial_results(db, event) if r.score is not None]
    names_result = await db.execute(
        select(Team.id, Team.name).where(Team.id.in_([r.team_id for r in rows]))
    )
    names = dict(names_result.tuples().all())
    ranks = competition_ranks([(r.team_id, r.score or 0.0) for r in rows])
    rows.sort(key=lambda r: (ranks[r.team_id], names.get(r.team_id) or ""))
    return [
        {
            "rank": ranks[r.team_id],
            "team_id": r.team_id,
            "team_name": names.get(r.team_id),
            "run1": r.run1,
            "run2": r.run2,
            "run3": r.run3,
            "run4": r.run4,
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
    row.doc_score = documentation_score(row.part1, row.part2, row.part3, row.onsite)


async def _rerank_docs(db: AsyncSession, event: Event) -> None:
    rows = await get_doc_scores(db, event)
    ranks = competition_ranks([(r.team_id, r.doc_score) for r in rows if r.doc_score is not None])
    for r in rows:
        r.doc_rank = ranks.get(r.team_id)
    await db.flush()


async def upsert_doc_score(
    db: AsyncSession,
    event: Event,
    data: dict,
    changed_by: str | None = None,
    *,
    rerank: bool = True,
) -> DocumentationScore:
    row = await _upsert(
        db, DocumentationScore, event, data, _DOC_FIELDS, "doc", changed_by, _derive_doc
    )
    if rerank:
        await _rerank_docs(db, event)
        await _refresh(db, [row])
    return row


async def bulk_upsert_doc_scores(
    db: AsyncSession, event: Event, entries: list[dict], changed_by: str | None = None
) -> list[DocumentationScore]:
    rows = [await upsert_doc_score(db, event, e, changed_by, rerank=False) for e in entries]
    await _rerank_docs(db, event)
    await _refresh(db, rows)
    return rows
