"""
Service logic for DE, aerial, documentation scoring and overall ranking.
"""
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from modules.scoring.competition_models import DEResult, AerialResult, DocumentationScore
from modules.scoring.models import Ranking
from modules.teams.models import Team, TeamSeasonRegistration
from modules.paper_review.models import Paper


def _avg_best_n(values: list[float], n: int = 2) -> float:
    valid = sorted([v for v in values if v is not None], reverse=True)
    if not valid:
        return 0.0
    return sum(valid[:n]) / n


def _normalize(values: list[float]) -> list[float]:
    """Normalize a list of raw values to 0-1 range."""
    valid = [v for v in values if v is not None]
    if not valid:
        return [0.0] * len(values)
    mx = max(valid)
    if mx == 0:
        return [0.0] * len(values)
    return [(v / mx if v is not None else 0.0) for v in values]


# ── Team helpers ──────────────────────────────────────────────────────────────

async def _team_map(db: AsyncSession, season_id: str) -> dict[str, dict]:
    """Returns {team_id: {name, category}} for all teams registered in season."""
    result = await db.execute(
        select(Team.id, Team.name, TeamSeasonRegistration.category)
        .join(TeamSeasonRegistration, TeamSeasonRegistration.team_id == Team.id)
        .where(TeamSeasonRegistration.season_id == season_id)
    )
    return {row.id: {"name": row.name, "category": row.category} for row in result}


# ── Double Elimination ────────────────────────────────────────────────────────

async def get_de_results(db: AsyncSession, season_id: str) -> list[DEResult]:
    result = await db.execute(
        select(DEResult).where(DEResult.season_id == season_id)
    )
    return list(result.scalars())


async def upsert_de_result(db: AsyncSession, season_id: str, data: dict) -> DEResult:
    existing = await db.execute(
        select(DEResult).where(
            DEResult.season_id == season_id,
            DEResult.team_id == data["team_id"],
        )
    )
    row = existing.scalar_one_or_none()
    if row is None:
        row = DEResult(season_id=season_id, **data)
        db.add(row)
    else:
        for k, v in data.items():
            setattr(row, k, v)
    await db.flush()
    return row


async def bulk_upsert_de_results(db: AsyncSession, season_id: str, entries: list[dict]) -> list[DEResult]:
    rows = [await upsert_de_result(db, season_id, e) for e in entries]
    # Recompute ranks per bracket
    for bracket in ("A", "B"):
        bracket_rows = sorted(
            [r for r in rows if r.bracket == bracket and r.de_rank is not None],
            key=lambda r: r.de_rank,
        )
        max_rank = len(bracket_rows)
        for r in bracket_rows:
            if r.de_rank and max_rank > 1:
                r.bracket_score = 1 - (r.de_rank - 1) / (max_rank - 1)
            elif max_rank == 1:
                r.bracket_score = 1.0
    return rows


# ── Aerial ────────────────────────────────────────────────────────────────────

async def get_aerial_results(db: AsyncSession, season_id: str) -> list[AerialResult]:
    result = await db.execute(
        select(AerialResult).where(AerialResult.season_id == season_id)
    )
    return list(result.scalars())


async def upsert_aerial_result(db: AsyncSession, season_id: str, data: dict) -> AerialResult:
    existing = await db.execute(
        select(AerialResult).where(
            AerialResult.season_id == season_id,
            AerialResult.team_id == data["team_id"],
        )
    )
    row = existing.scalar_one_or_none()
    if row is None:
        row = AerialResult(season_id=season_id, **data)
        db.add(row)
    else:
        for k, v in data.items():
            setattr(row, k, v)
    # Compute score: average of best 2 runs
    runs = [row.run1, row.run2, row.run3, row.run4]
    row.score = _avg_best_n([r for r in runs if r is not None], n=2)
    await db.flush()
    return row


async def bulk_upsert_aerial_results(db: AsyncSession, season_id: str, entries: list[dict]) -> list[AerialResult]:
    rows = [await upsert_aerial_result(db, season_id, e) for e in entries]
    # Rank by score descending
    scored = sorted([r for r in rows if r.score is not None], key=lambda r: r.score, reverse=True)
    for i, r in enumerate(scored, 1):
        r.rank = i
    return rows


# ── Documentation ─────────────────────────────────────────────────────────────

async def get_doc_scores(db: AsyncSession, season_id: str) -> list[DocumentationScore]:
    result = await db.execute(
        select(DocumentationScore).where(DocumentationScore.season_id == season_id)
    )
    return list(result.scalars())


async def upsert_doc_score(db: AsyncSession, season_id: str, data: dict) -> DocumentationScore:
    existing = await db.execute(
        select(DocumentationScore).where(
            DocumentationScore.season_id == season_id,
            DocumentationScore.team_id == data["team_id"],
        )
    )
    row = existing.scalar_one_or_none()
    if row is None:
        row = DocumentationScore(season_id=season_id, **data)
        db.add(row)
    else:
        for k, v in data.items():
            setattr(row, k, v)
    # Compute doc_score as average of available parts (0-1)
    parts = [row.part1, row.part2, row.part3]
    valid = [p / 100.0 for p in parts if p is not None]
    row.doc_score = sum(valid) / len(valid) if valid else None
    await db.flush()
    return row


async def bulk_upsert_doc_scores(db: AsyncSession, season_id: str, entries: list[dict]) -> list[DocumentationScore]:
    rows = [await upsert_doc_score(db, season_id, e) for e in entries]
    scored = sorted([r for r in rows if r.doc_score is not None], key=lambda r: r.doc_score, reverse=True)
    for i, r in enumerate(scored, 1):
        r.doc_rank = i
    return rows


# ── Overall Ranking ───────────────────────────────────────────────────────────

async def get_overall_ranking(
    db: AsyncSession,
    season_id: str,
    use_seeding: bool,
    use_double_elimination: bool,
    use_paper_scoring: bool,
    use_documentation_scoring: bool,
) -> list[dict]:
    """Compute combined overall ranking from enabled modules."""
    teams = await _team_map(db, season_id)
    if not teams:
        return []

    # Gather per-module scores keyed by team_id
    seed_scores: dict[str, float] = {}
    if use_seeding:
        result = await db.execute(
            select(Ranking).where(Ranking.season_id == season_id)
        )
        for r in result.scalars():
            seed_scores[r.team_id] = r.seed_score

    de_scores: dict[str, float] = {}
    if use_double_elimination:
        result = await db.execute(
            select(DEResult).where(DEResult.season_id == season_id)
        )
        for r in result.scalars():
            if r.de_score is not None:
                de_scores[r.team_id] = r.de_score

    paper_scores: dict[str, float] = {}
    if use_paper_scoring:
        result = await db.execute(
            select(Paper).where(Paper.season_id == season_id, Paper.final_score.isnot(None))
        )
        for p in result.scalars():
            paper_scores[p.team_id] = p.final_score

    doc_scores: dict[str, float] = {}
    if use_documentation_scoring:
        result = await db.execute(
            select(DocumentationScore).where(DocumentationScore.season_id == season_id)
        )
        for d in result.scalars():
            if d.doc_score is not None:
                doc_scores[d.team_id] = d.doc_score

    # Combine scores
    entries = []
    for team_id, info in teams.items():
        s = seed_scores.get(team_id, 0.0) if use_seeding else None
        d = de_scores.get(team_id, 0.0) if use_double_elimination else None
        p = paper_scores.get(team_id, 0.0) if use_paper_scoring else None
        doc = doc_scores.get(team_id, 0.0) if use_documentation_scoring else None

        parts = [v for v in [s, d, p, doc] if v is not None]
        overall = sum(parts)

        entries.append({
            "team_id": team_id,
            "team_name": info["name"],
            "category": info["category"],
            "overall_score": overall,
            "seeding_score": s,
            "de_score": d,
            "paper_score": p,
            "doc_score": doc,
            "aerial_score": None,
        })

    entries.sort(key=lambda e: e["overall_score"], reverse=True)
    for i, e in enumerate(entries, 1):
        e["rank"] = i

    return entries


async def get_aerial_ranking(db: AsyncSession, season_id: str) -> list[dict]:
    """Aerial ranking with team info."""
    teams = await _team_map(db, season_id)
    result = await db.execute(
        select(AerialResult).where(AerialResult.season_id == season_id)
    )
    rows = list(result.scalars())
    scored = sorted([r for r in rows if r.score is not None], key=lambda r: r.score, reverse=True)
    out = []
    for i, r in enumerate(scored, 1):
        info = teams.get(r.team_id, {})
        out.append({
            "rank": i,
            "team_id": r.team_id,
            "team_name": info.get("name"),
            "run1": r.run1, "run2": r.run2, "run3": r.run3, "run4": r.run4,
            "score": r.score,
        })
    return out
