from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import (
    assert_team_access,
    get_current_user,
    has_elevated_access,
    own_team_ids,
    require_any_permission,
    require_permission,
)
from core.database import get_db
from core.exceptions import ForbiddenError, NotFoundError
from core.rate_limit import rate_limit
from modules.events.module_access import require_module
from modules.teams import compliance, documents, service
from modules.teams.schemas import (
    MENTOR_SEASON_FIELDS,
    MENTOR_TEAM_FIELDS,
    ComplianceCheckUpdate,
    ComplianceItemCreate,
    ComplianceItemResponse,
    ComplianceItemUpdate,
    ComplianceStatusResponse,
    ComplianceVerify,
    TeamCreate,
    TeamDocumentResponse,
    TeamDocumentUpdate,
    TeamEventHistoryResponse,
    TeamListItem,
    TeamMemberCreate,
    TeamMemberResponse,
    TeamMemberUpdate,
    TeamResponse,
    TeamSeasonMemberResponse,
    TeamSeasonRegistrationCreate,
    TeamSeasonRegistrationResponse,
    TeamSeasonRosterUpdate,
    TeamSeasonUpdate,
    TeamUpdate,
)

router = APIRouter(prefix="/teams", tags=["teams"])


# Organizers of the print module work with the checklist as well.
_COMPLIANCE_ADMIN = ("teams:admin", "printing:admin")
# The 3D-print checklist belongs to the printing module: seasons whose events
# all have printing switched off answer 404 (modules.events.module_access).
_PRINTING = [Depends(require_module("printing"))]


async def _can_see_team_internals(db: AsyncSession, user, team_id: str) -> bool:
    """Organizers and the team itself; guests and other mentors are not."""
    return await has_elevated_access(db, user, "teams:admin") or team_id in await own_team_ids(
        db, user
    )


async def _assert_team_private(db: AsyncSession, user, team_id: str, elevated="teams:admin"):
    """Team-private data (documents, checklist): 404 for everyone else, so
    the existence of another team's records is not revealed."""
    await service.get_team(db, team_id)
    try:
        await assert_team_access(db, user, team_id, elevated)
    except ForbiddenError:
        raise NotFoundError("Not found") from None


def _registration_response(reg, *, full: bool) -> TeamSeasonRegistrationResponse:
    """Contact person and address are for the team and the organizers only."""
    resp = TeamSeasonRegistrationResponse.model_validate(reg)
    if not full:
        resp.contact_name = None
        resp.contact_email = None
        resp.contact_phone = None
        resp.address = None
    return resp


@router.get("", response_model=list[TeamListItem])
async def list_teams(
    season_id: str | None = Query(None),
    competition_level_id: str | None = Query(None),
    q: str | None = Query(None, max_length=200, description="Name, number, school or city"),
    country: str | None = Query(None, max_length=100),
    status: str | None = Query(None, pattern="^(active|archived)$"),
    category: str | None = Query(None, pattern="^(botball|open|aerial|jbc)$"),
    _=Depends(require_permission("teams:read")),
    db: AsyncSession = Depends(get_db),
):
    """Teams, searchable by name/number/school/city and filterable by country,
    status (active/archived), season and the season's team type."""
    return await service.list_teams(
        db,
        season_id,
        competition_level_id,
        q=q,
        country=country,
        status=status,
        category=category,
    )


@router.get("/countries", response_model=list[str])
async def list_team_countries(
    _=Depends(require_permission("teams:read")),
    db: AsyncSession = Depends(get_db),
):
    return await service.list_countries(db)


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
    current_user=Depends(require_permission("teams:read")),
    db: AsyncSession = Depends(get_db),
):
    registrations = await service.list_registrations(db, season_id, team_id)
    is_admin = await has_elevated_access(db, current_user, "teams:admin")
    own = set() if is_admin else await own_team_ids(db, current_user)
    return [
        _registration_response(reg, full=is_admin or reg.team_id in own) for reg in registrations
    ]


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


# ── 3D-print checklist configuration ──────────────────────────────────────────


@router.get(
    "/print-compliance/items", response_model=list[ComplianceItemResponse], dependencies=_PRINTING
)
async def list_compliance_items(
    season_id: str = Query(...),
    include_inactive: bool = Query(False),
    current_user=Depends(require_permission("teams:read")),
    db: AsyncSession = Depends(get_db),
):
    """The season's checklist items (the competition rules for printed parts)."""
    if include_inactive and not await has_elevated_access(db, current_user, _COMPLIANCE_ADMIN):
        include_inactive = False
    return await compliance.list_items(db, season_id, include_inactive)


@router.post(
    "/print-compliance/items",
    response_model=ComplianceItemResponse,
    status_code=201,
    dependencies=_PRINTING,
)
async def create_compliance_item(
    body: ComplianceItemCreate,
    _=Depends(require_any_permission(*_COMPLIANCE_ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    return await compliance.create_item(db, body.model_dump())


@router.post(
    "/print-compliance/items/defaults",
    response_model=list[ComplianceItemResponse],
    status_code=201,
    dependencies=_PRINTING,
)
async def seed_compliance_items(
    season_id: str = Query(...),
    _=Depends(require_any_permission(*_COMPLIANCE_ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    """Start a season's checklist from the general 3D-print rules (module 04)."""
    return await compliance.seed_default_items(db, season_id)


@router.patch(
    "/print-compliance/items/{item_id}",
    response_model=ComplianceItemResponse,
    dependencies=_PRINTING,
)
async def update_compliance_item(
    item_id: str,
    body: ComplianceItemUpdate,
    _=Depends(require_any_permission(*_COMPLIANCE_ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    return await compliance.update_item(db, item_id, body.model_dump(exclude_unset=True))


@router.delete("/print-compliance/items/{item_id}", status_code=204, dependencies=_PRINTING)
async def delete_compliance_item(
    item_id: str,
    _=Depends(require_any_permission(*_COMPLIANCE_ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    await compliance.delete_item(db, item_id)


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
    changes = body.model_dump(exclude_unset=True)
    if not await has_elevated_access(db, current_user, "teams:admin"):
        # Mentors edit the team profile only. Organizer fields sent back
        # unchanged (as an edit form does) are no change and pass.
        team = await service.get_team(db, team_id)
        forbidden = sorted(
            key
            for key, value in changes.items()
            if key not in MENTOR_TEAM_FIELDS and getattr(team, key) != value
        )
        if forbidden:
            raise ForbiddenError(f"Only organizers may change: {', '.join(forbidden)}")
    return await service.update_team(db, team_id, **changes)


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


# ── Season participation ──────────────────────────────────────────────────────


@router.get("/{team_id}/seasons", response_model=list[TeamSeasonRegistrationResponse])
async def list_team_seasons(
    team_id: str,
    current_user=Depends(require_permission("teams:read")),
    db: AsyncSession = Depends(get_db),
):
    """Every season the team took part in, with its registration details."""
    await service.get_team(db, team_id)
    full = await _can_see_team_internals(db, current_user, team_id)
    return [
        _registration_response(reg, full=full)
        for reg in await service.list_registrations(db, team_id=team_id)
    ]


@router.get("/{team_id}/seasons/{season_id}", response_model=TeamSeasonRegistrationResponse)
async def get_team_season(
    team_id: str,
    season_id: str,
    current_user=Depends(require_permission("teams:read")),
    db: AsyncSession = Depends(get_db),
):
    reg = await service.get_season_registration(db, team_id, season_id)
    return _registration_response(
        reg, full=await _can_see_team_internals(db, current_user, team_id)
    )


@router.put("/{team_id}/seasons/{season_id}", response_model=TeamSeasonRegistrationResponse)
async def update_team_season(
    team_id: str,
    season_id: str,
    body: TeamSeasonUpdate,
    current_user=Depends(require_permission("teams:write")),
    db: AsyncSession = Depends(get_db),
):
    """Edit a season registration.

    Organizers (teams:admin) edit everything: team type, fee and kit status,
    confirmation, notes. A mentor may only keep the contact person and the
    address of their own team up to date.
    """
    await assert_team_access(db, current_user, team_id, "teams:admin")
    changes = body.model_dump(exclude_unset=True)
    if "contact_email" in changes and changes["contact_email"] is not None:
        changes["contact_email"] = str(changes["contact_email"])
    if not await has_elevated_access(db, current_user, "teams:admin"):
        forbidden = sorted(set(changes) - MENTOR_SEASON_FIELDS)
        if forbidden:
            raise ForbiddenError(f"Only organizers may change: {', '.join(forbidden)}")
    reg = await service.update_season_registration(db, team_id, season_id, changes)
    return _registration_response(reg, full=True)


@router.get("/{team_id}/seasons/{season_id}/members", response_model=list[TeamSeasonMemberResponse])
async def get_season_roster(
    team_id: str,
    season_id: str,
    _=Depends(require_permission("teams:read")),
    db: AsyncSession = Depends(get_db),
):
    """Who was on the team in this season (names and season roles only)."""
    return await service.get_season_roster(db, team_id, season_id)


@router.put("/{team_id}/seasons/{season_id}/members", response_model=list[TeamSeasonMemberResponse])
async def set_season_roster(
    team_id: str,
    season_id: str,
    body: TeamSeasonRosterUpdate,
    current_user=Depends(require_permission("teams:write")),
    db: AsyncSession = Depends(get_db),
):
    await assert_team_access(db, current_user, team_id, "teams:admin")
    return await service.set_season_roster(
        db, team_id, season_id, [m.model_dump() for m in body.members]
    )


# ── 3D-print checklist of a team ──────────────────────────────────────────────


@router.get(
    "/{team_id}/seasons/{season_id}/print-compliance",
    response_model=ComplianceStatusResponse,
    dependencies=_PRINTING,
)
async def get_print_compliance(
    team_id: str,
    season_id: str,
    current_user=Depends(require_any_permission("teams:read", "printing:read")),
    db: AsyncSession = Depends(get_db),
):
    await _assert_team_private(db, current_user, team_id, _COMPLIANCE_ADMIN)
    return await compliance.team_status(db, team_id, season_id)


@router.put(
    "/{team_id}/seasons/{season_id}/print-compliance/verify",
    response_model=ComplianceStatusResponse,
    dependencies=_PRINTING,
)
async def verify_print_compliance(
    team_id: str,
    season_id: str,
    body: ComplianceVerify,
    current_user=Depends(require_any_permission(*_COMPLIANCE_ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    """Organizer confirms (or withdraws) the team's completed checklist."""
    await service.get_team(db, team_id)
    return await compliance.verify(
        db, team_id, season_id, verified=body.verified, user_id=current_user.id
    )


@router.put(
    "/{team_id}/seasons/{season_id}/print-compliance/{item_id}",
    response_model=ComplianceStatusResponse,
    dependencies=_PRINTING,
)
async def set_print_compliance_check(
    team_id: str,
    season_id: str,
    item_id: str,
    body: ComplianceCheckUpdate,
    current_user=Depends(require_any_permission("teams:write", *_COMPLIANCE_ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    """Tick (or untick) one checklist item for the team."""
    await _assert_team_private(db, current_user, team_id, _COMPLIANCE_ADMIN)
    return await compliance.set_check(
        db,
        team_id,
        season_id,
        item_id,
        checked=body.checked,
        note=body.note,
        user_id=current_user.id,
    )


# ── Documents ─────────────────────────────────────────────────────────────────


@router.get("/{team_id}/documents", response_model=list[TeamDocumentResponse])
async def list_team_documents(
    team_id: str,
    season_id: str | None = Query(None),
    current_user=Depends(require_permission("teams:read")),
    db: AsyncSession = Depends(get_db),
):
    """The team's documents with all versions (own team and organizers only)."""
    await _assert_team_private(db, current_user, team_id)
    return await documents.list_documents(db, team_id, season_id)


@router.post(
    "/{team_id}/documents",
    response_model=TeamDocumentResponse,
    status_code=201,
    dependencies=[Depends(rate_limit("team-document-upload", 20, 60))],
)
async def upload_team_document(
    team_id: str,
    file: UploadFile = File(...),
    title: str = Form(..., min_length=1, max_length=255),
    category: str = Form("other"),
    season_id: str | None = Form(None),
    description: str | None = Form(None),
    current_user=Depends(require_permission("teams:write")),
    db: AsyncSession = Depends(get_db),
):
    """Upload a new document (PDF or image) as its version 1."""
    await _assert_team_private(db, current_user, team_id)
    return await documents.create_document(
        db,
        team_id,
        title=title,
        category=category,
        season_id=season_id or None,
        description=description,
        file=file,
        uploaded_by=current_user.id,
    )


@router.post(
    "/{team_id}/documents/{document_id}/versions",
    response_model=TeamDocumentResponse,
    status_code=201,
    dependencies=[Depends(rate_limit("team-document-upload", 20, 60))],
)
async def upload_team_document_version(
    team_id: str,
    document_id: str,
    file: UploadFile = File(...),
    comment: str | None = Form(None),
    current_user=Depends(require_permission("teams:write")),
    db: AsyncSession = Depends(get_db),
):
    """Upload a new version; earlier versions stay in the archive."""
    await _assert_team_private(db, current_user, team_id)
    return await documents.add_version(
        db, team_id, document_id, file, current_user.id, comment=comment
    )


@router.patch("/{team_id}/documents/{document_id}", response_model=TeamDocumentResponse)
async def update_team_document(
    team_id: str,
    document_id: str,
    body: TeamDocumentUpdate,
    current_user=Depends(require_permission("teams:write")),
    db: AsyncSession = Depends(get_db),
):
    await _assert_team_private(db, current_user, team_id)
    return await documents.update_document(
        db, team_id, document_id, body.model_dump(exclude_unset=True)
    )


@router.delete("/{team_id}/documents/{document_id}", status_code=204)
async def delete_team_document(
    team_id: str,
    document_id: str,
    current_user=Depends(require_permission("teams:write")),
    db: AsyncSession = Depends(get_db),
):
    """Delete a document with all its versions."""
    await _assert_team_private(db, current_user, team_id)
    await documents.delete_document(db, team_id, document_id)


@router.get("/{team_id}/documents/{document_id}/download")
async def download_team_document(
    team_id: str,
    document_id: str,
    version: int | None = Query(None, ge=1),
    current_user=Depends(require_permission("teams:read")),
    db: AsyncSession = Depends(get_db),
):
    """Download one version (default: the latest) as an attachment."""
    await _assert_team_private(db, current_user, team_id)
    document = await documents.get_document(db, team_id, document_id)
    path, file_name, media_type = documents.version_file(document, version)
    return FileResponse(
        str(path),
        filename=file_name,
        media_type=media_type,
        content_disposition_type="attachment",
    )
