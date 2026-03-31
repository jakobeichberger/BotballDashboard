from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import get_current_user, require_permission
from core.database import get_db
from modules.printing import service
from modules.printing.schemas import (
    FilamentSpoolCreate,
    FilamentSpoolResponse,
    PrinterCreate,
    PrinterResponse,
    PrinterUpdate,
    PrintJobCreate,
    PrintJobResponse,
    PrintJobUpdate,
    QuotaResponse,
)

router = APIRouter(prefix="/printing", tags=["printing"])


# ── Printers ──────────────────────────────────────────────────────────────────

@router.get("/printers", response_model=list[PrinterResponse])
async def list_printers(
    _=Depends(require_permission("printing:read")), db: AsyncSession = Depends(get_db)
):
    return await service.list_printers(db)


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

@router.get("/jobs", response_model=list[PrintJobResponse])
async def list_print_jobs(
    season_id: str | None = Query(None),
    team_id: str | None = Query(None),
    status: str | None = Query(None),
    _=Depends(require_permission("printing:read")),
    db: AsyncSession = Depends(get_db),
):
    return await service.list_print_jobs(db, season_id, team_id, status)


@router.post("/jobs", response_model=PrintJobResponse, status_code=201)
async def create_print_job(
    body: PrintJobCreate,
    current_user=Depends(require_permission("printing:write")),
    db: AsyncSession = Depends(get_db),
):
    return await service.create_print_job(db, body.model_dump(), current_user.id)


@router.patch("/jobs/{job_id}", response_model=PrintJobResponse)
async def update_print_job(
    job_id: str,
    body: PrintJobUpdate,
    _=Depends(require_permission("printing:admin")),
    db: AsyncSession = Depends(get_db),
):
    return await service.update_print_job(db, job_id, **body.model_dump(exclude_none=True))


@router.put("/jobs/{job_id}/approve", response_model=PrintJobResponse)
async def approve_print_job(
    job_id: str,
    current_user=Depends(require_permission("printing:admin")),
    db: AsyncSession = Depends(get_db),
):
    return await service.approve_print_job(db, job_id, current_user.id)


# ── Quotas ────────────────────────────────────────────────────────────────────

@router.get("/quotas", response_model=QuotaResponse)
async def get_quota(
    team_id: str = Query(...),
    season_id: str = Query(...),
    _=Depends(require_permission("printing:read")),
    db: AsyncSession = Depends(get_db),
):
    return await service.get_quota(db, team_id, season_id)


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
