from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.domain_events import emit_event
from core.exceptions import ConflictError, NotFoundError
from modules.printing.crypto import decrypt_credential, encrypt_credential
from modules.printing.models import FilamentSpool, Printer, PrintJob, TeamSeasonPrintQuota
from modules.scoring.service import get_default_event, resolve_event

JOB_TRANSITIONS = {
    "pending": {"approved", "cancelled"},
    "approved": {"queued", "cancelled"},
    "queued": {"printing", "completed", "failed", "cancelled"},
    "printing": {"completed", "failed", "cancelled"},
    "failed": {"queued", "cancelled"},
    "completed": set(),
    "cancelled": set(),
}

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
    event_id: str | None = None,
) -> list[PrintJob]:
    q = select(PrintJob).order_by(PrintJob.priority.desc(), PrintJob.created_at)
    if season_id:
        q = q.where(PrintJob.season_id == season_id)
    if team_id:
        q = q.where(PrintJob.team_id == team_id)
    if status:
        q = q.where(PrintJob.status == status)
    if event_id:
        q = q.where(PrintJob.event_id == event_id)
    result = await db.execute(q)
    return list(result.scalars().all())


async def get_print_job(db: AsyncSession, job_id: str) -> PrintJob:
    result = await db.execute(select(PrintJob).where(PrintJob.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise NotFoundError("Print job not found")
    return job


async def create_print_job(db: AsyncSession, data: dict, submitted_by: str) -> PrintJob:
    event = await resolve_event(db, data["season_id"], data.get("event_id"))
    data["event_id"] = event.id
    from modules.events.models import EventRegistration

    registration = await db.execute(
        select(EventRegistration.id).where(
            EventRegistration.event_id == event.id,
            EventRegistration.team_id == data["team_id"],
        )
    )
    if not registration.scalar_one_or_none():
        raise ConflictError("Team must be registered for the event before submitting print jobs")
    # Check quota
    quota = await _get_or_create_quota(db, data["team_id"], data["season_id"], event.id)
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
    new_status = kwargs.get("status")
    if new_status and new_status != old_status and new_status not in JOB_TRANSITIONS[old_status]:
        raise ConflictError(f"Invalid print job transition: {old_status} -> {new_status}")

    for key, value in kwargs.items():
        if value is not None:
            setattr(job, key, value)

    now = datetime.now(UTC)
    if kwargs.get("status") == "printing" and old_status != "printing":
        job.started_at = now
    if kwargs.get("status") == "completed" and old_status != "completed":
        job.completed_at = now
        await _update_quota_usage(db, job)

    if new_status and new_status != old_status:
        await emit_event(
            db,
            "print_status_changed",
            event_id=job.event_id,
            payload={
                "jobId": job.id,
                "status": new_status,
                "userId": job.submitted_by,
                "message": f"Print job {job.file_name}: {new_status}",
            },
        )

    return job


async def approve_print_job(db: AsyncSession, job_id: str, approved_by: str) -> PrintJob:
    job = await get_print_job(db, job_id)
    if "approved" not in JOB_TRANSITIONS[job.status]:
        raise ConflictError(f"Print job cannot be approved from {job.status}")
    await update_print_job(db, job.id, status="approved")
    job.approved_by = approved_by
    job.approved_at = datetime.now(UTC)
    return job


async def _get_or_create_quota(
    db: AsyncSession, team_id: str, season_id: str, event_id: str | None = None
) -> TeamSeasonPrintQuota:
    result = await db.execute(
        select(TeamSeasonPrintQuota).where(
            TeamSeasonPrintQuota.team_id == team_id,
            TeamSeasonPrintQuota.event_id == event_id
            if event_id
            else TeamSeasonPrintQuota.season_id == season_id,
        )
    )
    quota = result.scalar_one_or_none()
    if not quota:
        quota = TeamSeasonPrintQuota(team_id=team_id, season_id=season_id, event_id=event_id)
        db.add(quota)
        await db.flush()
    return quota


async def _update_quota_usage(db: AsyncSession, job: PrintJob) -> None:
    quota = await _get_or_create_quota(db, job.team_id, job.season_id, job.event_id)
    quota.used_parts += 1
    if job.actual_grams:
        quota.used_grams += job.actual_grams


async def get_quota(
    db: AsyncSession, team_id: str, season_id: str, event_id: str | None = None
) -> TeamSeasonPrintQuota:
    event = (
        await resolve_event(db, season_id, event_id)
        if event_id
        else await get_default_event(db, season_id)
    )
    return await _get_or_create_quota(db, team_id, season_id, event.id)


async def apply_printer_status(db: AsyncSession, printer: Printer, status) -> None:
    printer.is_online = status.online
    printer.last_seen = datetime.now(UTC) if status.online else printer.last_seen
    result = await db.execute(
        select(PrintJob)
        .where(
            PrintJob.printer_id == printer.id,
            PrintJob.status.in_(("queued", "printing")),
        )
        .order_by(PrintJob.created_at)
    )
    job = result.scalars().first()
    if not job:
        return
    job.progress = status.progress
    job.status_message = status.message
    job.last_polled_at = datetime.now(UTC)
    target = status.state if status.state in ("printing", "completed", "failed") else None
    if target and target != job.status and target in JOB_TRANSITIONS[job.status]:
        await update_print_job(db, job.id, status=target)


# ── Filament spools ───────────────────────────────────────────────────────────


async def list_spools(db: AsyncSession, printer_id: str | None = None) -> list[FilamentSpool]:
    q = select(FilamentSpool).where(FilamentSpool.is_active == True)
    if printer_id:
        q = q.where(FilamentSpool.printer_id == printer_id)
    result = await db.execute(q)
    return list(result.scalars().all())


async def create_spool(db: AsyncSession, data: dict) -> FilamentSpool:
    spool_data = data.copy()
    spool_data.setdefault("remaining_grams", spool_data.get("initial_grams", 1000.0))
    spool = FilamentSpool(**spool_data)
    db.add(spool)
    return spool


async def consume_filament(db: AsyncSession, spool_id: str, grams: float) -> FilamentSpool:
    result = await db.execute(select(FilamentSpool).where(FilamentSpool.id == spool_id))
    spool = result.scalar_one_or_none()
    if not spool:
        raise NotFoundError("Filament spool not found")
    spool.remaining_grams = max(0.0, spool.remaining_grams - grams)
    return spool
