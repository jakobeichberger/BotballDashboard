from fastapi import APIRouter, Depends
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import get_current_user, has_elevated_access, require_permission
from core.database import get_db
from core.files import safe_filename
from modules.seasons import portability, service
from modules.seasons.schemas import (
    CompetitionLevelCreate,
    CompetitionLevelResponse,
    CompetitionLevelUpdate,
    SeasonClone,
    SeasonCreate,
    SeasonEventCreate,
    SeasonEventResponse,
    SeasonListItem,
    SeasonResponse,
    SeasonUpdate,
)

router = APIRouter(prefix="/seasons", tags=["seasons"])


async def _sees_drafts(db: AsyncSession, user) -> bool:
    """Draft seasons are work in progress – only season editors see them."""
    return await has_elevated_access(db, user, "seasons:write")


@router.get("", response_model=list[SeasonListItem])
async def list_seasons(
    current_user=Depends(require_permission("seasons:read")), db: AsyncSession = Depends(get_db)
):
    return await service.list_seasons(db, include_drafts=await _sees_drafts(db, current_user))


@router.get("/active", response_model=SeasonResponse | None)
async def get_active_season(_=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await service.get_active_season(db)


@router.post("", response_model=SeasonResponse, status_code=201)
async def create_season(
    body: SeasonCreate,
    _=Depends(require_permission("seasons:write")),
    db: AsyncSession = Depends(get_db),
):
    phases = [p.model_dump() for p in body.phases]
    data = body.model_dump(exclude={"phases", "create_default_event"})
    return await service.create_season(db, data, phases, body.create_default_event)


@router.get("/{season_id}", response_model=SeasonResponse)
async def get_season(
    season_id: str,
    current_user=Depends(require_permission("seasons:read")),
    db: AsyncSession = Depends(get_db),
):
    return await service.get_season(
        db, season_id, include_drafts=await _sees_drafts(db, current_user)
    )


@router.post("/{season_id}/clone", response_model=SeasonResponse, status_code=201)
async def clone_season(
    season_id: str,
    body: SeasonClone,
    _=Depends(require_permission("seasons:write")),
    db: AsyncSession = Depends(get_db),
):
    """Copy a season's configuration (not its results) into a new draft season."""
    return await portability.clone_season(db, season_id, body.name, body.year)


@router.get("/{season_id}/export.json")
async def export_season(
    season_id: str,
    _=Depends(require_permission("seasons:write")),
    db: AsyncSession = Depends(get_db),
):
    """Complete JSON snapshot of the season (events, registrations, results, …)."""
    data = await portability.export_season(db, season_id)
    file_name = safe_filename(f"season-{season_id}.json", "season.json")
    return JSONResponse(
        jsonable_encoder(data),
        headers={"Content-Disposition": f'attachment; filename="{file_name}"'},
    )


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
    include_inactive: bool = False, _=Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    return await service.list_competition_levels(db, include_inactive)


@router.post("/competition-levels", response_model=CompetitionLevelResponse, status_code=201)
async def create_competition_level(
    body: CompetitionLevelCreate,
    _=Depends(require_permission("seasons:write")),
    db: AsyncSession = Depends(get_db),
):
    return await service.create_competition_level(db, body.model_dump())


@router.patch("/competition-levels/{level_id}", response_model=CompetitionLevelResponse)
async def update_competition_level(
    level_id: str,
    body: CompetitionLevelUpdate,
    _=Depends(require_permission("seasons:write")),
    db: AsyncSession = Depends(get_db),
):
    data = body.model_dump(exclude_none=True)
    if "qualifies_from_level_id" in body.model_fields_set:
        data["qualifies_from_level_id"] = body.qualifies_from_level_id
    return await service.update_competition_level(db, level_id, **data)


@router.delete("/competition-levels/{level_id}", status_code=204)
async def delete_competition_level(
    level_id: str,
    _=Depends(require_permission("seasons:write")),
    db: AsyncSession = Depends(get_db),
):
    await service.delete_competition_level(db, level_id)


# ── Season events / deadlines ──────────────────────────────────────────────────


@router.get("/{season_id}/events", response_model=list[SeasonEventResponse])
async def list_season_events(
    season_id: str,
    current_user=Depends(require_permission("seasons:read")),
    db: AsyncSession = Depends(get_db),
):
    await service.get_season(db, season_id, include_drafts=await _sees_drafts(db, current_user))
    return await service.list_events(db, season_id)


@router.post("/{season_id}/events", response_model=SeasonEventResponse, status_code=201)
async def create_season_event(
    season_id: str,
    body: SeasonEventCreate,
    _=Depends(require_permission("seasons:write")),
    db: AsyncSession = Depends(get_db),
):
    return await service.create_event(db, season_id, body.model_dump())


@router.delete("/{season_id}/events/{event_id}", status_code=204)
async def delete_season_event(
    season_id: str,
    event_id: str,
    _=Depends(require_permission("seasons:write")),
    db: AsyncSession = Depends(get_db),
):
    await service.delete_event(db, season_id, event_id)
