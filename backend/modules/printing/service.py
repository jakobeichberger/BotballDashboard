from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.exceptions import ConflictError, NotFoundError
from modules.printing.crypto import decrypt_credential, encrypt_credential
from modules.printing.models import FilamentSpool, PrintJob, Printer, TeamSeasonPrintQuota


# ── Printers ──────────────────────────────────────────────────────────────────

async def list_printers(db: AsyncSession) -> list[Printer]:
    result = await db.execute(select(Printer).order_by(Printer.name))
    return list(result.scalars().all())


async def get_printer(db: AsyncSession, printer_id: str) -> Printer:
    result = await db.execute(select(Printer).where(Printer.id == printer_id))
    printer = result.scalar_one_or_none()
    if not printer:
        raise NotFoundError("Printer not found")
    return printer


async def create_printer(db: AsyncSession, data: dict) -> Printer:
    api_key = data.pop("api_key", None)
    printer = Printer(**data)
    if api_key:
        printer.api_key_encrypted = encrypt_credential(api_key)
    db.add(printer)
    return printer


async def update_printer(db: AsyncSession, printer_id: str, **kwargs) -> Printer:
    printer = await get_printer(db, printer_id)
    api_key = kwargs.pop("api_key", None)
    for key, value in kwargs.items():
        if value is not None:
            setattr(printer, key, value)
    if api_key:
        printer.api_key_encrypted = encrypt_credential(api_key)
    return printer


async def get_printer_api_key(db: AsyncSession, printer_id: str) -> str:
    printer = await get_printer(db, printer_id)
    if not printer.api_key_encrypted:
        return ""
    return decrypt_credential(printer.api_key_encrypted)


# ── Print Jobs ────────────────────────────────────────────────────────────────

async def list_print_jobs(
    db: AsyncSession,
    season_id: str | None = None,
    team_id: str | None = None,
    status: str | None = None,
) -> list[PrintJob]:
    q = select(PrintJob).order_by(PrintJob.priority.desc(), PrintJob.created_at)
    if season_id:
        q = q.where(PrintJob.season_id == season_id)
    if team_id:
        q = q.where(PrintJob.team_id == team_id)
    if status:
        q = q.where(PrintJob.status == status)
    result = await db.execute(q)
    return list(result.scalars().all())


async def get_print_job(db: AsyncSession, job_id: str) -> PrintJob:
    result = await db.execute(select(PrintJob).where(PrintJob.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise NotFoundError("Print job not found")
    return job


async def create_print_job(db: AsyncSession, data: dict, submitted_by: str) -> PrintJob:
    # Check quota
    quota = await _get_or_create_quota(db, data["team_id"], data["season_id"])
    if quota.used_parts >= quota.max_parts:
        raise ConflictError(
            f"Hard print limit reached ({quota.max_parts} parts). Cannot submit more jobs."
        )

    job = PrintJob(**data, submitted_by=submitted_by)
    db.add(job)
    return job


async def update_print_job(db: AsyncSession, job_id: str, **kwargs) -> PrintJob:
    job = await get_print_job(db, job_id)
    old_status = job.status

    for key, value in kwargs.items():
        if value is not None:
            setattr(job, key, value)

    now = datetime.now(timezone.utc)
    if kwargs.get("status") == "printing" and old_status != "printing":
        job.started_at = now
    if kwargs.get("status") == "completed" and old_status != "completed":
        job.completed_at = now
        await _update_quota_usage(db, job)

    return job


async def approve_print_job(db: AsyncSession, job_id: str, approved_by: str) -> PrintJob:
    job = await get_print_job(db, job_id)
    job.status = "approved"
    job.approved_by = approved_by
    job.approved_at = datetime.now(timezone.utc)
    return job


async def _get_or_create_quota(
    db: AsyncSession, team_id: str, season_id: str
) -> TeamSeasonPrintQuota:
    result = await db.execute(
        select(TeamSeasonPrintQuota).where(
            TeamSeasonPrintQuota.team_id == team_id,
            TeamSeasonPrintQuota.season_id == season_id,
        )
    )
    quota = result.scalar_one_or_none()
    if not quota:
        quota = TeamSeasonPrintQuota(team_id=team_id, season_id=season_id)
        db.add(quota)
        await db.flush()
    return quota


async def _update_quota_usage(db: AsyncSession, job: PrintJob) -> None:
    quota = await _get_or_create_quota(db, job.team_id, job.season_id)
    quota.used_parts += 1
    if job.actual_grams:
        quota.used_grams += job.actual_grams


async def get_quota(db: AsyncSession, team_id: str, season_id: str) -> TeamSeasonPrintQuota:
    return await _get_or_create_quota(db, team_id, season_id)


# ── Filament spools ───────────────────────────────────────────────────────────

async def list_spools(db: AsyncSession, printer_id: str | None = None) -> list[FilamentSpool]:
    q = select(FilamentSpool).where(FilamentSpool.is_active == True)
    if printer_id:
        q = q.where(FilamentSpool.printer_id == printer_id)
    result = await db.execute(q)
    return list(result.scalars().all())


async def create_spool(db: AsyncSession, data: dict) -> FilamentSpool:
    spool = FilamentSpool(**data)
    db.add(spool)
    return spool


async def consume_filament(db: AsyncSession, spool_id: str, grams: float) -> FilamentSpool:
    result = await db.execute(select(FilamentSpool).where(FilamentSpool.id == spool_id))
    spool = result.scalar_one_or_none()
    if not spool:
        raise NotFoundError("Filament spool not found")
    spool.remaining_grams = max(0.0, spool.remaining_grams - grams)
    return spool
