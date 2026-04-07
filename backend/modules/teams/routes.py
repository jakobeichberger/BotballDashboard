from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import require_permission, require_any_permission
from core.database import get_db
from modules.teams import service
from modules.teams.schemas import (
    TeamCreate,
    TeamListItem,
    TeamMemberCreate,
    TeamMemberResponse,
    TeamResponse,
    TeamSeasonRegistrationCreate,
    TeamSeasonRegistrationResponse,
    TeamUpdate,
)

router = APIRouter(prefix="/teams", tags=["teams"])


@router.get("", response_model=list[TeamListItem])
async def list_teams(
    season_id: str | None = Query(None),
    competition_level_id: str | None = Query(None),
    _=Depends(require_permission("teams:read")),
    db: AsyncSession = Depends(get_db),
):
    return await service.list_teams(db, season_id, competition_level_id)


@router.post("", response_model=TeamResponse, status_code=201)
async def create_team(
    body: TeamCreate,
    _=Depends(require_permission("teams:write")),
    db: AsyncSession = Depends(get_db),
):
    members = [m.model_dump() for m in body.members]
    data = body.model_dump(exclude={"members"})
    return await service.create_team(db, data, members)


# ── Season registrations (must come before /{team_id} to avoid path shadowing) ─

@router.get("/registrations", response_model=list[TeamSeasonRegistrationResponse])
async def list_registrations(
    season_id: str | None = Query(None),
    team_id: str | None = Query(None),
    _=Depends(require_permission("teams:read")),
    db: AsyncSession = Depends(get_db),
):
    return await service.list_registrations(db, season_id, team_id)


@router.post("/registrations", response_model=TeamSeasonRegistrationResponse, status_code=201)
async def register_for_season(
    body: TeamSeasonRegistrationCreate,
    _=Depends(require_permission("teams:write")),
    db: AsyncSession = Depends(get_db),
):
    return await service.register_for_season(
        db, body.team_id, body.season_id,
        competition_level_id=body.competition_level_id,
        notes=body.notes,
    )


@router.put("/registrations/{registration_id}/confirm", response_model=TeamSeasonRegistrationResponse)
async def confirm_registration(
    registration_id: str,
    _=Depends(require_permission("teams:write")),
    db: AsyncSession = Depends(get_db),
):
    return await service.confirm_registration(db, registration_id)


# ── Individual team routes ────────────────────────────────────────────────────

@router.get("/{team_id}", response_model=TeamResponse)
async def get_team(
    team_id: str,
    _=Depends(require_permission("teams:read")),
    db: AsyncSession = Depends(get_db),
):
    return await service.get_team(db, team_id)


@router.patch("/{team_id}", response_model=TeamResponse)
async def update_team(
    team_id: str,
    body: TeamUpdate,
    _=Depends(require_permission("teams:write")),
    db: AsyncSession = Depends(get_db),
):
    return await service.update_team(db, team_id, **body.model_dump(exclude_none=True))


@router.delete("/{team_id}", status_code=204)
async def delete_team(
    team_id: str,
    _=Depends(require_permission("teams:write")),
    db: AsyncSession = Depends(get_db),
):
    await service.delete_team(db, team_id)


@router.post("/{team_id}/members", response_model=TeamMemberResponse, status_code=201)
async def add_member(
    team_id: str,
    body: TeamMemberCreate,
    _=Depends(require_permission("teams:write")),
    db: AsyncSession = Depends(get_db),
):
    return await service.add_member(db, team_id, body.model_dump())


@router.delete("/{team_id}/members/{member_id}", status_code=204)
async def remove_member(
    team_id: str,
    member_id: str,
    _=Depends(require_permission("teams:write")),
    db: AsyncSession = Depends(get_db),
):
    await service.remove_member(db, team_id, member_id)
