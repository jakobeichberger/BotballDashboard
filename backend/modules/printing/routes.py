from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import (
    assert_team_access,
    has_elevated_access,
    own_team_ids,
    require_any_permission,
    require_permission,
)
from core.database import get_db
from core.exceptions import ForbiddenError, NotFoundError
from core.rate_limit import rate_limit
from modules.printing import files, service
from modules.printing.schemas import (
    FilamentSpoolCreate,
    FilamentSpoolResponse,
    PrinterCreate,
    PrinterPublicResponse,
    PrinterResponse,
    PrinterUpdate,
    PrintJobCancelResponse,
    PrintJobCreate,
    PrintJobCreateResponse,
    PrintJobReject,
    PrintJobResponse,
    PrintJobUpdate,
    QuotaResponse,
    QuotaUpsert,
    RobotPartsSummary,
)

router = APIRouter(prefix="/printing", tags=["printing"])


# ── Printers ──────────────────────────────────────────────────────────────────


@router.get("/printers", response_model=list[PrinterResponse])
async def list_printers(
    current_user=Depends(require_permission("printing:read")),
    db: AsyncSession = Depends(get_db),
):
    printers = await service.list_printers(db)
    if await has_elevated_access(db, current_user, "printing:admin"):
        return printers
    # Mentors see the live status, never URLs, serials or notes.
    return [PrinterPublicResponse.model_validate(p) for p in printers]


@router.post("/printers", response_model=PrinterResponse, status_code=201)
async def create_printer(
    body: PrinterCreate,
    _=Depends(require_permission("printing:admin")),
    db: AsyncSession = Depends(get_db),
):
    return await service.create_printer(db, body.model_dump())


@router.patch("/printers/{printer_id}", response_model=PrinterResponse)
async def update_printer(
    printer_id: str,
    body: PrinterUpdate,
    _=Depends(require_permission("printing:admin")),
    db: AsyncSession = Depends(get_db),
):
    return await service.update_printer(db, printer_id, **body.model_dump(exclude_none=True))


# ── Print jobs ────────────────────────────────────────────────────────────────


async def _get_visible_job(db: AsyncSession, current_user, job_id: str):
    job = await service.get_print_job(db, job_id)
    try:
        await assert_team_access(db, current_user, job.team_id, "printing:admin")
    except ForbiddenError:
        # Do not reveal that another team's job exists.
        raise NotFoundError("Print job not found") from None
    return job


@router.get("/jobs", response_model=list[PrintJobResponse])
async def list_print_jobs(
    season_id: str | None = Query(None),
    team_id: str | None = Query(None),
    status: str | None = Query(None),
    event_id: str | None = Query(None),
    current_user=Depends(require_permission("printing:read")),
    db: AsyncSession = Depends(get_db),
):
    # Mentors hold printing:read too; they see their own teams' jobs only.
    team_ids = None
    if not await has_elevated_access(db, current_user, "printing:admin"):
        team_ids = await own_team_ids(db, current_user)
    return await service.list_print_jobs(db, season_id, team_id, status, event_id, team_ids)


@router.post("/jobs", response_model=PrintJobCreateResponse, status_code=201)
async def create_print_job(
    body: PrintJobCreate,
    current_user=Depends(require_permission("printing:write")),
    db: AsyncSession = Depends(get_db),
):
    # Organizers (printing:admin) may submit for any team; mentors only their own.
    await assert_team_access(db, current_user, body.team_id, "printing:admin")
    if body.quota_override and not await has_elevated_access(db, current_user, "printing:admin"):
        raise ForbiddenError("Only print admins may override the print quota")
    job = await service.create_print_job(db, body.model_dump(), current_user.id)
    warning = await service.quota_warning(db, job)
    from modules.teams.compliance import compliance_warning

    return PrintJobCreateResponse.model_validate(job).model_copy(
        update={
            "quota_warning": warning,
            "compliance_warning": await compliance_warning(db, job.team_id, job.season_id),
        }
    )


@router.get("/jobs/{job_id}", response_model=PrintJobResponse)
async def get_print_job(
    job_id: str,
    current_user=Depends(require_permission("printing:read")),
    db: AsyncSession = Depends(get_db),
):
    return await _get_visible_job(db, current_user, job_id)


@router.patch("/jobs/{job_id}", response_model=PrintJobResponse)
async def update_print_job(
    job_id: str,
    body: PrintJobUpdate,
    current_user=Depends(require_permission("printing:admin")),
    db: AsyncSession = Depends(get_db),
):
    await service.ensure_job_writable(db, await service.get_print_job(db, job_id))
    return await service.update_print_job(
        db, job_id, acting_user_id=current_user.id, **body.model_dump(exclude_none=True)
    )


@router.put("/jobs/{job_id}/approve", response_model=PrintJobResponse)
async def approve_print_job(
    job_id: str,
    current_user=Depends(require_permission("printing:admin")),
    db: AsyncSession = Depends(get_db),
):
    return await service.approve_print_job(db, job_id, current_user.id)


@router.put("/jobs/{job_id}/reject", response_model=PrintJobResponse)
async def reject_print_job(
    job_id: str,
    body: PrintJobReject,
    _=Depends(require_permission("printing:admin")),
    db: AsyncSession = Depends(get_db),
):
    return await service.reject_print_job(db, job_id, body.reason)


@router.put("/jobs/{job_id}/cancel", response_model=PrintJobCancelResponse)
async def cancel_print_job(
    job_id: str,
    current_user=Depends(require_any_permission("printing:write", "printing:admin")),
    db: AsyncSession = Depends(get_db),
):
    """Cancel a job. A running print is aborted on the printer as well; the
    response says whether that worked (printer_cancel / printer_message)."""
    job = await _get_visible_job(db, current_user, job_id)
    as_admin = await has_elevated_access(db, current_user, "printing:admin")
    job, printer_result = await service.cancel_print_job(
        db, job.id, as_admin=as_admin, user_id=current_user.id
    )
    return PrintJobCancelResponse.model_validate(job).model_copy(update=printer_result)


@router.post(
    "/jobs/{job_id}/file",
    response_model=PrintJobResponse,
    dependencies=[Depends(rate_limit("print-upload", 20, 60))],
)
async def upload_print_file(
    job_id: str,
    file: UploadFile = File(...),
    current_user=Depends(require_any_permission("printing:write", "printing:admin")),
    db: AsyncSession = Depends(get_db),
):
    # Check the record and the caller's access before anything touches the disk.
    job = await _get_visible_job(db, current_user, job_id)
    await service.ensure_job_writable(db, job)
    as_admin = await has_elevated_access(db, current_user, "printing:admin")
    service.assert_file_replaceable(job, as_admin=as_admin)
    relative_path, file_name, size = await files.save_print_file(file, job.id)
    box = None
    if file_name.lower().endswith(".stl"):
        from modules.printing.rules import measure_stl

        box = await measure_stl(files.stored_path(job.id, file_name))
    return service.attach_file(job, relative_path, file_name, size, box)


@router.get("/teams/{team_id}/seasons/{season_id}/robot-parts", response_model=RobotPartsSummary)
async def get_robot_parts(
    team_id: str,
    season_id: str,
    current_user=Depends(require_permission("printing:read")),
    db: AsyncSession = Depends(get_db),
):
    """Printed robot parts against the game review's limit of six."""
    await assert_team_access(db, current_user, team_id, "printing:admin")
    return await service.robot_parts_summary(db, team_id, season_id)


@router.get("/jobs/{job_id}/file")
async def download_print_file(
    job_id: str,
    current_user=Depends(require_permission("printing:read")),
    db: AsyncSession = Depends(get_db),
):
    job = await _get_visible_job(db, current_user, job_id)
    if not job.file_path:
        raise NotFoundError("No file uploaded")
    path = files.stored_path(job.id, job.file_name)
    if not path.is_file():
        raise NotFoundError("File missing on the server")
    # Always a download: meshes and G-code are never rendered by the browser.
    return FileResponse(
        str(path),
        filename=path.name,
        media_type="application/octet-stream",
        content_disposition_type="attachment",
    )


# ── Quotas ────────────────────────────────────────────────────────────────────


@router.get("/quotas", response_model=QuotaResponse)
async def get_quota(
    team_id: str = Query(...),
    season_id: str = Query(...),
    event_id: str | None = Query(None),
    current_user=Depends(require_permission("printing:read")),
    db: AsyncSession = Depends(get_db),
):
    await assert_team_access(db, current_user, team_id, "printing:admin")
    quota = await service.get_quota(db, team_id, season_id, event_id)
    return await service.quota_summary(db, quota)


@router.get("/events/{event_id}/quotas", response_model=list[QuotaResponse])
async def list_event_quotas(
    event_id: str,
    _=Depends(require_permission("printing:admin")),
    db: AsyncSession = Depends(get_db),
):
    return await service.list_event_quotas(db, event_id)


@router.put("/quotas", response_model=QuotaResponse)
async def set_quota(
    body: QuotaUpsert,
    _=Depends(require_permission("printing:admin")),
    db: AsyncSession = Depends(get_db),
):
    quota = await service.set_quota(
        db,
        body.team_id,
        body.season_id,
        body.event_id,
        clear_max_grams=body.clear_max_grams,
        max_parts=body.max_parts,
        soft_limit_parts=body.soft_limit_parts,
        max_grams=body.max_grams,
        notes=body.notes,
    )
    return await service.quota_summary(db, quota)


# ── Filament spools ───────────────────────────────────────────────────────────


@router.get("/spools", response_model=list[FilamentSpoolResponse])
async def list_spools(
    printer_id: str | None = Query(None),
    _=Depends(require_permission("printing:admin")),
    db: AsyncSession = Depends(get_db),
):
    return await service.list_spools(db, printer_id)


@router.post("/spools", response_model=FilamentSpoolResponse, status_code=201)
async def create_spool(
    body: FilamentSpoolCreate,
    _=Depends(require_permission("printing:admin")),
    db: AsyncSession = Depends(get_db),
):
    return await service.create_spool(db, body.model_dump())


@router.post("/spools/{spool_id}/consume", response_model=FilamentSpoolResponse)
async def consume_filament(
    spool_id: str,
    grams: float = Query(..., gt=0),
    _=Depends(require_permission("printing:admin")),
    db: AsyncSession = Depends(get_db),
):
    return await service.consume_filament(db, spool_id, grams)
