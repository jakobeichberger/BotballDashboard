from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import get_current_user, require_permission
from core.database import get_db
from modules.seasons import service
from modules.seasons.schemas import (
    CompetitionLevelResponse,
    SeasonCreate,
    SeasonListItem,
    SeasonResponse,
    SeasonUpdate,
)

router = APIRouter(prefix="/seasons", tags=["seasons"])


@router.get("", response_model=list[SeasonListItem])
async def list_seasons(
    _=Depends(require_permission("seasons:read")), db: AsyncSession = Depends(get_db)
):
    return await service.list_seasons(db)


@router.get("/active", response_model=SeasonResponse | None)
async def get_active_season(
    _=Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    return await service.get_active_season(db)


@router.post("", response_model=SeasonResponse, status_code=201)
async def create_season(
    body: SeasonCreate,
    _=Depends(require_permission("seasons:write")),
    db: AsyncSession = Depends(get_db),
):
    phases = [p.model_dump() for p in body.phases]
    data = body.model_dump(exclude={"phases"})
    return await service.create_season(db, data, phases)


@router.get("/{season_id}", response_model=SeasonResponse)
async def get_season(
    season_id: str,
    _=Depends(require_permission("seasons:read")),
    db: AsyncSession = Depends(get_db),
):
    return await service.get_season(db, season_id)


@router.patch("/{season_id}", response_model=SeasonResponse)
async def update_season(
    season_id: str,
    body: SeasonUpdate,
    _=Depends(require_permission("seasons:write")),
    db: AsyncSession = Depends(get_db),
):
    return await service.update_season(db, season_id, **body.model_dump(exclude_none=True))


@router.put("/{season_id}/activate", response_model=SeasonResponse)
async def activate_season(
    season_id: str,
    _=Depends(require_permission("seasons:write")),
    db: AsyncSession = Depends(get_db),
):
    return await service.set_active_season(db, season_id)


@router.delete("/{season_id}", status_code=204)
async def delete_season(
    season_id: str,
    _=Depends(require_permission("seasons:write")),
    db: AsyncSession = Depends(get_db),
):
    await service.delete_season(db, season_id)


@router.put("/{season_id}/phases/{phase_id}/activate")
async def activate_phase(
    season_id: str,
    phase_id: str,
    _=Depends(require_permission("seasons:write")),
    db: AsyncSession = Depends(get_db),
):
    return await service.activate_phase(db, season_id, phase_id)


@router.get("/competition-levels/all", response_model=list[CompetitionLevelResponse])
async def list_competition_levels(
    _=Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    return await service.list_competition_levels(db)
