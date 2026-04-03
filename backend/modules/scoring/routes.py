import asyncio

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import get_current_user, require_permission, require_any_permission
from core.database import get_db
from modules.scoring import service
from modules.scoring import competition_service as comp_svc
from modules.scoring.schemas import (
    MatchCreate,
    MatchResponse,
    MatchUpdate,
    RankingResponse,
    ScoreBulkEntry,
)
from modules.scoring.competition_schemas import (
    DEResultUpsert,
    DEResultResponse,
    AerialResultUpsert,
    AerialResultResponse,
    DocScoreUpsert,
    DocScoreResponse,
    OverallRankingEntry,
    TeamRankingEntry,
)
from modules.seasons import service as season_svc

router = APIRouter(prefix="/scoring", tags=["scoring"])

# WebSocket connections for live scoreboard (set + lock for safe concurrent access)
_scoreboard_connections: set[WebSocket] = set()
_connection_lock = asyncio.Lock()


@router.websocket("/scoreboard/ws")
async def scoreboard_ws(websocket: WebSocket):
    await websocket.accept()
    async with _connection_lock:
        _scoreboard_connections.add(websocket)
    try:
        while True:
            await websocket.receive_text()  # keep-alive
    except WebSocketDisconnect:
        pass
    finally:
        async with _connection_lock:
            _scoreboard_connections.discard(websocket)


async def _broadcast_ranking_update(season_id: str) -> None:
    async with _connection_lock:
        dead: set[WebSocket] = set()
        for ws in list(_scoreboard_connections):
            try:
                await ws.send_json({"event": "ranking_updated", "season_id": season_id})
            except Exception:
                dead.add(ws)
        _scoreboard_connections.difference_update(dead)


# ── Matches ───────────────────────────────────────────────────────────────────

@router.get("/seasons/{season_id}/matches", response_model=list[MatchResponse])
async def list_matches(
    season_id: str,
    team_id: str | None = Query(None),
    phase_id: str | None = Query(None),
    _=Depends(require_permission("scoring:read")),
    db: AsyncSession = Depends(get_db),
):
    return await service.list_matches(db, season_id, team_id, phase_id)


@router.post("/seasons/{season_id}/matches", response_model=MatchResponse, status_code=201)
async def create_match(
    season_id: str,
    body: MatchCreate,
    current_user=Depends(require_permission("scoring:write")),
    db: AsyncSession = Depends(get_db),
):
    data = body.model_dump()
    data["season_id"] = season_id
    match = await service.create_match(db, data, current_user.id)
    await _broadcast_ranking_update(season_id)
    return match


@router.post("/seasons/{season_id}/matches/bulk", response_model=list[MatchResponse], status_code=201)
async def bulk_create_matches(
    season_id: str,
    body: ScoreBulkEntry,
    current_user=Depends(require_permission("scoring:write")),
    db: AsyncSession = Depends(get_db),
):
    results = []
    for entry in body.entries:
        data = entry.model_dump()
        data["season_id"] = season_id
        results.append(await service.create_match(db, data, current_user.id))
    await _broadcast_ranking_update(season_id)
    return results


@router.get("/matches/{match_id}", response_model=MatchResponse)
async def get_match(
    match_id: str,
    _=Depends(require_permission("scoring:read")),
    db: AsyncSession = Depends(get_db),
):
    return await service.get_match(db, match_id)


@router.patch("/matches/{match_id}", response_model=MatchResponse)
async def update_match(
    match_id: str,
    body: MatchUpdate,
    _=Depends(require_permission("scoring:write")),
    db: AsyncSession = Depends(get_db),
):
    match = await service.update_match(db, match_id, **body.model_dump(exclude_none=True))
    await _broadcast_ranking_update(match.season_id)
    return match


@router.put("/matches/{match_id}/confirm", response_model=MatchResponse)
async def confirm_match(
    match_id: str,
    current_user=Depends(require_permission("scoring:admin")),
    db: AsyncSession = Depends(get_db),
):
    return await service.confirm_match(db, match_id, current_user.id)


@router.delete("/matches/{match_id}", status_code=204)
async def delete_match(
    match_id: str,
    _=Depends(require_permission("scoring:admin")),
    db: AsyncSession = Depends(get_db),
):
    await service.delete_match(db, match_id)


# ── Ranking ───────────────────────────────────────────────────────────────────

@router.get("/seasons/{season_id}/ranking", response_model=list[RankingResponse])
async def get_ranking(
    season_id: str,
    competition_level_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Public endpoint – no auth required for scoreboard display."""
    return await service.get_ranking(db, season_id, competition_level_id)


# ── Enhanced Ranking (with team names + category) ─────────────────────────────

@router.get("/seasons/{season_id}/ranking/extended", response_model=list[TeamRankingEntry])
async def get_ranking_extended(
    season_id: str,
    category: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Seeding ranking enriched with team name and registration category."""
    from sqlalchemy import select
    from modules.scoring.models import Ranking
    from modules.teams.models import Team, TeamSeasonRegistration

    result = await db.execute(
        select(
            Ranking.rank,
            Ranking.team_id,
            Ranking.seed_score,
            Ranking.best_score,
            Ranking.average_score,
            Ranking.rounds_played,
            Team.name.label("team_name"),
            TeamSeasonRegistration.category,
        )
        .join(Team, Team.id == Ranking.team_id)
        .outerjoin(
            TeamSeasonRegistration,
            (TeamSeasonRegistration.team_id == Ranking.team_id)
            & (TeamSeasonRegistration.season_id == season_id),
        )
        .where(Ranking.season_id == season_id)
        .order_by(Ranking.rank)
    )
    rows = result.all()
    if category:
        rows = [r for r in rows if (r.category or "botball") == category]
    return [
        TeamRankingEntry(
            rank=r.rank,
            team_id=r.team_id,
            team_name=r.team_name,
            category=r.category or "botball",
            seed_score=r.seed_score,
            best_score=r.best_score,
            average_score=r.average_score,
            rounds_played=r.rounds_played,
        )
        for r in rows
    ]


# ── Overall Ranking ───────────────────────────────────────────────────────────

@router.get("/seasons/{season_id}/ranking/overall", response_model=list[OverallRankingEntry])
async def get_overall_ranking(
    season_id: str,
    category: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    season = await season_svc.get_season(db, season_id)
    entries = await comp_svc.get_overall_ranking(
        db,
        season_id,
        use_seeding=season.use_seeding,
        use_double_elimination=season.use_double_elimination,
        use_paper_scoring=season.use_paper_scoring,
        use_documentation_scoring=season.use_documentation_scoring,
    )
    if category:
        entries = [e for e in entries if e["category"] == category]
    return entries


# ── Double Elimination ────────────────────────────────────────────────────────

@router.get("/seasons/{season_id}/de-results", response_model=list[DEResultResponse])
async def list_de_results(
    season_id: str,
    _=Depends(require_permission("scoring:read")),
    db: AsyncSession = Depends(get_db),
):
    return await comp_svc.get_de_results(db, season_id)


@router.put("/seasons/{season_id}/de-results", response_model=list[DEResultResponse])
async def bulk_upsert_de_results(
    season_id: str,
    body: list[DEResultUpsert],
    _=Depends(require_permission("scoring:write")),
    db: AsyncSession = Depends(get_db),
):
    entries = [e.model_dump() for e in body]
    rows = await comp_svc.bulk_upsert_de_results(db, season_id, entries)
    await _broadcast_ranking_update(season_id)
    return rows


@router.put("/seasons/{season_id}/de-results/{team_id}", response_model=DEResultResponse)
async def upsert_de_result(
    season_id: str,
    team_id: str,
    body: DEResultUpsert,
    _=Depends(require_permission("scoring:write")),
    db: AsyncSession = Depends(get_db),
):
    data = body.model_dump()
    data["team_id"] = team_id
    return await comp_svc.upsert_de_result(db, season_id, data)


# ── Aerial ────────────────────────────────────────────────────────────────────

@router.get("/seasons/{season_id}/aerial-results", response_model=list[AerialResultResponse])
async def list_aerial_results(
    season_id: str,
    _=Depends(require_permission("scoring:read")),
    db: AsyncSession = Depends(get_db),
):
    return await comp_svc.get_aerial_results(db, season_id)


@router.get("/seasons/{season_id}/aerial-ranking")
async def get_aerial_ranking(
    season_id: str,
    db: AsyncSession = Depends(get_db),
):
    return await comp_svc.get_aerial_ranking(db, season_id)


@router.put("/seasons/{season_id}/aerial-results", response_model=list[AerialResultResponse])
async def bulk_upsert_aerial_results(
    season_id: str,
    body: list[AerialResultUpsert],
    _=Depends(require_permission("scoring:write")),
    db: AsyncSession = Depends(get_db),
):
    entries = [e.model_dump() for e in body]
    return await comp_svc.bulk_upsert_aerial_results(db, season_id, entries)


@router.put("/seasons/{season_id}/aerial-results/{team_id}", response_model=AerialResultResponse)
async def upsert_aerial_result(
    season_id: str,
    team_id: str,
    body: AerialResultUpsert,
    _=Depends(require_permission("scoring:write")),
    db: AsyncSession = Depends(get_db),
):
    data = body.model_dump()
    data["team_id"] = team_id
    return await comp_svc.upsert_aerial_result(db, season_id, data)


# ── Documentation Scoring ─────────────────────────────────────────────────────

@router.get("/seasons/{season_id}/doc-scores", response_model=list[DocScoreResponse])
async def list_doc_scores(
    season_id: str,
    _=Depends(require_permission("scoring:read")),
    db: AsyncSession = Depends(get_db),
):
    return await comp_svc.get_doc_scores(db, season_id)


@router.put("/seasons/{season_id}/doc-scores", response_model=list[DocScoreResponse])
async def bulk_upsert_doc_scores(
    season_id: str,
    body: list[DocScoreUpsert],
    _=Depends(require_permission("scoring:write")),
    db: AsyncSession = Depends(get_db),
):
    entries = [e.model_dump() for e in body]
    return await comp_svc.bulk_upsert_doc_scores(db, season_id, entries)


@router.put("/seasons/{season_id}/doc-scores/{team_id}", response_model=DocScoreResponse)
async def upsert_doc_score(
    season_id: str,
    team_id: str,
    body: DocScoreUpsert,
    _=Depends(require_permission("scoring:write")),
    db: AsyncSession = Depends(get_db),
):
    data = body.model_dump()
    data["team_id"] = team_id
    return await comp_svc.upsert_doc_score(db, season_id, data)
