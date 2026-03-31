import asyncio

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import get_current_user, require_permission, require_any_permission
from core.database import get_db
from modules.scoring import service
from modules.scoring.schemas import (
    MatchCreate,
    MatchResponse,
    MatchUpdate,
    RankingResponse,
    ScoreBulkEntry,
)

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
