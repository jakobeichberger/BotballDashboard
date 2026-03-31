"""Scoring service: match CRUD + ranking computation."""
from datetime import datetime, timezone

from sqlalchemy import select, delete, func as sqlfunc
from sqlalchemy.ext.asyncio import AsyncSession

from core.exceptions import NotFoundError
from modules.scoring.models import Match, Ranking, ScoringSchema


# ── Score formulas ────────────────────────────────────────────────────────────

def compute_seed_score(scores: list[float]) -> float:
    """Average of the top 2 scores (or fewer if less available)."""
    if not scores:
        return 0.0
    top = sorted(scores, reverse=True)[:2]
    return sum(top) / len(top)


def compute_match_total(raw_scores: dict, schema_fields: list[dict]) -> float:
    """Multiply each field value by its multiplier and sum."""
    total = 0.0
    field_map = {f["key"]: f for f in schema_fields}
    for key, value in raw_scores.items():
        field = field_map.get(key, {})
        multiplier = field.get("multiplier", 1)
        total += float(value) * float(multiplier)
    return round(total, 2)


# ── Schemas ───────────────────────────────────────────────────────────────────

async def get_active_schema(
    db: AsyncSession, season_id: str, competition_level_id: str | None = None
) -> ScoringSchema | None:
    q = select(ScoringSchema).where(
        ScoringSchema.season_id == season_id,
        ScoringSchema.is_active == True,
    )
    if competition_level_id:
        q = q.where(ScoringSchema.competition_level_id == competition_level_id)
    result = await db.execute(q.order_by(ScoringSchema.version.desc()))
    return result.scalar_one_or_none()


# ── Matches ───────────────────────────────────────────────────────────────────

async def list_matches(
    db: AsyncSession,
    season_id: str,
    team_id: str | None = None,
    phase_id: str | None = None,
) -> list[Match]:
    q = select(Match).where(Match.season_id == season_id).order_by(
        Match.round_number, Match.created_at
    )
    if team_id:
        q = q.where(Match.team_id == team_id)
    if phase_id:
        q = q.where(Match.phase_id == phase_id)
    result = await db.execute(q)
    return list(result.scalars().all())


async def get_match(db: AsyncSession, match_id: str) -> Match:
    result = await db.execute(select(Match).where(Match.id == match_id))
    match = result.scalar_one_or_none()
    if not match:
        raise NotFoundError("Match not found")
    return match


async def create_match(db: AsyncSession, data: dict, entered_by: str) -> Match:
    schema = await get_active_schema(db, data["season_id"], data.get("competition_level_id"))
    schema_fields = schema.fields if schema else []

    raw_scores = data.get("raw_scores", {})
    total = compute_match_total(raw_scores, schema_fields)

    match = Match(**data, total_score=total, entered_by=entered_by)
    db.add(match)
    await db.flush()
    await _recompute_ranking(db, data["season_id"], data["team_id"], data.get("competition_level_id"))
    return match


async def update_match(db: AsyncSession, match_id: str, **kwargs) -> Match:
    match = await get_match(db, match_id)
    if "raw_scores" in kwargs:
        schema = await get_active_schema(db, match.season_id, match.competition_level_id)
        schema_fields = schema.fields if schema else []
        kwargs["total_score"] = compute_match_total(kwargs["raw_scores"], schema_fields)

    for key, value in kwargs.items():
        if value is not None:
            setattr(match, key, value)

    await _recompute_ranking(db, match.season_id, match.team_id, match.competition_level_id)
    return match


async def confirm_match(db: AsyncSession, match_id: str, confirmed_by: str) -> Match:
    match = await get_match(db, match_id)
    match.confirmed_by = confirmed_by
    match.confirmed_at = datetime.now(timezone.utc)
    return match


async def delete_match(db: AsyncSession, match_id: str) -> None:
    match = await get_match(db, match_id)
    season_id, team_id, level_id = match.season_id, match.team_id, match.competition_level_id
    await db.delete(match)
    await db.flush()
    await _recompute_ranking(db, season_id, team_id, level_id)


# ── Ranking ───────────────────────────────────────────────────────────────────

async def _recompute_ranking(
    db: AsyncSession, season_id: str, team_id: str, competition_level_id: str | None
) -> None:
    result = await db.execute(
        select(Match).where(
            Match.season_id == season_id,
            Match.team_id == team_id,
            Match.is_disqualified == False,
        )
    )
    matches = result.scalars().all()
    scores = [m.total_score for m in matches]

    if not scores:
        await db.execute(
            delete(Ranking).where(
                Ranking.season_id == season_id,
                Ranking.team_id == team_id,
            )
        )
        return

    seed_score = compute_seed_score(scores)
    best_score = max(scores)
    avg_score = sum(scores) / len(scores)

    # Upsert ranking row for this team
    result = await db.execute(
        select(Ranking).where(
            Ranking.season_id == season_id,
            Ranking.team_id == team_id,
        )
    )
    ranking = result.scalar_one_or_none()
    if ranking:
        ranking.seed_score = seed_score
        ranking.best_score = best_score
        ranking.average_score = avg_score
        ranking.rounds_played = len(scores)
    else:
        ranking = Ranking(
            season_id=season_id,
            team_id=team_id,
            competition_level_id=competition_level_id,
            rank=0,
            seed_score=seed_score,
            best_score=best_score,
            average_score=avg_score,
            rounds_played=len(scores),
        )
        db.add(ranking)

    await db.flush()
    await _refresh_ranks(db, season_id, competition_level_id)


async def _refresh_ranks(
    db: AsyncSession, season_id: str, competition_level_id: str | None
) -> None:
    """Re-number all ranks for a season/level by seed_score DESC."""
    q = select(Ranking).where(Ranking.season_id == season_id)
    if competition_level_id:
        q = q.where(Ranking.competition_level_id == competition_level_id)
    result = await db.execute(q.order_by(Ranking.seed_score.desc()))
    rankings = result.scalars().all()
    for i, r in enumerate(rankings, start=1):
        r.rank = i


async def get_ranking(
    db: AsyncSession, season_id: str, competition_level_id: str | None = None
) -> list[Ranking]:
    q = select(Ranking).where(Ranking.season_id == season_id).order_by(Ranking.rank)
    if competition_level_id:
        q = q.where(Ranking.competition_level_id == competition_level_id)
    result = await db.execute(q)
    return list(result.scalars().all())
