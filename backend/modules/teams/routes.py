from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import (
    assert_team_access,
    get_current_user,
    has_elevated_access,
    own_team_ids,
    require_permission,
)
from core.database import get_db
from core.exceptions import ForbiddenError
from modules.teams import service
from modules.teams.schemas import (
    TeamCreate,
    TeamEventHistoryResponse,
    TeamListItem,
    TeamMemberCreate,
    TeamMemberResponse,
    TeamMemberUpdate,
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


@router.get("/mine", response_model=list[TeamListItem])
async def list_my_teams(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Teams the current user belongs to — used for mentor self-service dropdowns."""
    return await service.list_my_teams(db, current_user.id)


@router.post("", response_model=TeamResponse, status_code=201)
async def create_team(
    body: TeamCreate,
    _=Depends(require_permission("teams:admin")),
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
    current_user=Depends(require_permission("teams:write")),
    db: AsyncSession = Depends(get_db),
):
    # Mentors may register their own team; organizers any team.
    await assert_team_access(db, current_user, body.team_id, "teams:admin")
    return await service.register_for_season(
        db,
        body.team_id,
        body.season_id,
        # Organizers may register late (or early); mentors only within the
        # season's registration window.
        enforce_window=not await has_elevated_access(db, current_user, "teams:admin"),
        competition_level_id=body.competition_level_id,
        notes=body.notes,
    )


@router.put(
    "/registrations/{registration_id}/confirm", response_model=TeamSeasonRegistrationResponse
)
async def confirm_registration(
    registration_id: str,
    _=Depends(require_permission("teams:admin")),
    db: AsyncSession = Depends(get_db),
):
    return await service.confirm_registration(db, registration_id)


@router.delete("/registrations/{registration_id}", status_code=204)
async def delete_registration(
    registration_id: str,
    _=Depends(require_permission("teams:admin")),
    db: AsyncSession = Depends(get_db),
):
    await service.delete_registration(db, registration_id)


# ── Individual team routes ────────────────────────────────────────────────────


@router.get("/{team_id}/history", response_model=list[TeamEventHistoryResponse])
async def get_team_history(
    team_id: str,
    _=Depends(require_permission("teams:read")),
    db: AsyncSession = Depends(get_db),
):
    return await service.get_team_history(db, team_id)


@router.get("/{team_id}", response_model=TeamResponse)
async def get_team(
    team_id: str,
    current_user=Depends(require_permission("teams:read")),
    db: AsyncSession = Depends(get_db),
):
    resp = TeamResponse.model_validate(await service.get_team(db, team_id))
    # teams:read reaches guests and every mentor. Member e-mail addresses (mostly
    # students) and the organizers' notes are only for the team itself and admins.
    if not await has_elevated_access(
        db, current_user, "teams:admin"
    ) and team_id not in await own_team_ids(db, current_user):
        resp.notes = None
        for member in resp.members:
            member.email = None
    return resp


@router.patch("/{team_id}", response_model=TeamResponse)
async def update_team(
    team_id: str,
    body: TeamUpdate,
    current_user=Depends(require_permission("teams:write")),
    db: AsyncSession = Depends(get_db),
):
    await assert_team_access(db, current_user, team_id, "teams:admin")
    return await service.update_team(db, team_id, **body.model_dump(exclude_unset=True))


@router.delete("/{team_id}", status_code=204)
async def delete_team(
    team_id: str,
    _=Depends(require_permission("teams:admin")),
    db: AsyncSession = Depends(get_db),
):
    await service.delete_team(db, team_id)


@router.post("/{team_id}/members", response_model=TeamMemberResponse, status_code=201)
async def add_member(
    team_id: str,
    body: TeamMemberCreate,
    current_user=Depends(require_permission("teams:write")),
    db: AsyncSession = Depends(get_db),
):
    await assert_team_access(db, current_user, team_id, "teams:admin")
    if body.user_id and not await has_elevated_access(db, current_user, "teams:admin"):
        raise ForbiddenError("Only team administrators may link user accounts")
    return await service.add_member(db, team_id, body.model_dump())


@router.patch("/{team_id}/members/{member_id}", response_model=TeamMemberResponse)
async def update_member(
    team_id: str,
    member_id: str,
    body: TeamMemberUpdate,
    current_user=Depends(require_permission("teams:write")),
    db: AsyncSession = Depends(get_db),
):
    """Edit a member. Linking or unlinking a user account (user_id) decides
    who acts for the team, so only teams:admin may change it; a mentor can
    still correct name, e-mail and role of their own team's members."""
    await assert_team_access(db, current_user, team_id, "teams:admin")
    changes = body.model_dump(exclude_unset=True)
    if "user_id" in changes and not await has_elevated_access(db, current_user, "teams:admin"):
        raise ForbiddenError("Only team administrators may link user accounts")
    return await service.update_member(db, team_id, member_id, changes)


@router.delete("/{team_id}/members/{member_id}", status_code=204)
async def remove_member(
    team_id: str,
    member_id: str,
    current_user=Depends(require_permission("teams:write")),
    db: AsyncSession = Depends(get_db),
):
    await assert_team_access(db, current_user, team_id, "teams:admin")
    await service.remove_member(db, team_id, member_id)
