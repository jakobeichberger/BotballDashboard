import asyncio
from datetime import UTC, datetime

from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from core.audit import log_action
from core.domain_events import emit_event
from core.exceptions import ConflictError, NotFoundError
from core.logging import get_logger
from modules.printing.adapters import cancel_printer_job
from modules.printing.crypto import decrypt_credential, encrypt_credential
from modules.printing.models import FilamentSpool, Printer, PrintJob, TeamSeasonPrintQuota
from modules.scoring.service import get_default_event, resolve_event
from modules.seasons.lifecycle import ensure_writable

logger = get_logger(__name__)

JOB_TRANSITIONS = {
    "pending": {"approved", "rejected", "cancelled"},
    "approved": {"queued", "rejected", "cancelled"},
    # queued -> completed covers manually operated (generic) printers.
    "queued": {"printing", "completed", "failed", "cancelled"},
    "printing": {"completed", "failed", "cancelled"},
    "failed": {"queued", "cancelled"},
    "completed": set(),
    "cancelled": set(),
    "rejected": set(),
}

# Submitted jobs that are not finished yet. They count toward the hard limit
# together with completed parts, otherwise a team could queue any number of
# jobs before the first one completes.
OPEN_STATUSES = ("pending", "approved", "queued", "printing")

# An OctoPrint/Bambu printer that is idle again after printing finished the job
# when it got (almost) to the end; below that the print was stopped on the device.
_DONE_PROGRESS = 99.0

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
    await db.flush()
    await db.refresh(printer)
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


# ── Print Jobs ────────────────────────────────────────────────────────────────


async def list_print_jobs(
    db: AsyncSession,
    season_id: str | None = None,
    team_id: str | None = None,
    status: str | None = None,
    event_id: str | None = None,
    team_ids: set[str] | None = None,
) -> list[PrintJob]:
    """`team_ids`, when given, limits the result to those teams (mentor scoping)."""
    q = select(PrintJob).order_by(PrintJob.priority.desc(), PrintJob.created_at)
    if season_id:
        q = q.where(PrintJob.season_id == season_id)
    if team_id:
        q = q.where(PrintJob.team_id == team_id)
    if status:
        q = q.where(PrintJob.status == status)
    if event_id:
        q = q.where(PrintJob.event_id == event_id)
    if team_ids is not None:
        q = q.where(PrintJob.team_id.in_(team_ids))
    result = await db.execute(q)
    return list(result.scalars().all())


async def get_print_job(db: AsyncSession, job_id: str) -> PrintJob:
    result = await db.execute(select(PrintJob).where(PrintJob.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise NotFoundError("Print job not found")
    return job


async def create_print_job(db: AsyncSession, data: dict, submitted_by: str) -> PrintJob:
    """Create a pending job after checking the team's hard limits.

    ``data["quota_override"]`` lets the job through although a hard limit is
    reached; the caller must have checked that the user holds printing:admin.
    The job then carries ``quota_override=True`` and an audit entry is written.
    """
    data = data.copy()
    override = bool(data.pop("quota_override", False))
    requested_event_id = data.get("event_id")
    await ensure_writable(db, season_id=data["season_id"])
    event = await resolve_event(db, data["season_id"], data.get("event_id"))
    await ensure_writable(db, event_id=event.id)
    data["event_id"] = event.id
    from modules.events.models import EventRegistration

    registration = await db.execute(
        select(EventRegistration.id).where(
            EventRegistration.event_id == event.id,
            EventRegistration.team_id == data["team_id"],
        )
    )
    if not registration.scalar_one_or_none():
        if requested_event_id:
            raise ConflictError(
                "Team must be registered for the event before submitting print jobs"
            )
        from modules.events.service import ensure_legacy_default_registration

        await ensure_legacy_default_registration(db, event, data["team_id"])

    quota = await _locked_quota(db, data["team_id"], data["season_id"], event.id)
    violation = await _hard_limit_violation(db, quota, data.get("estimated_grams"))
    if violation and not override:
        raise ConflictError(violation)

    job = PrintJob(**data, submitted_by=submitted_by, quota_override=bool(violation))
    db.add(job)
    await db.flush()
    await db.refresh(job)
    if violation:
        await log_action(
            db,
            "printing.quota_override",
            user_id=submitted_by,
            resource_type="print_job",
            resource_id=job.id,
            detail={"team_id": job.team_id, "event_id": job.event_id, "reason": violation},
        )
    return job


async def quota_warning(db: AsyncSession, job: PrintJob) -> str | None:
    """Warning for a freshly created job: soft limit exceeded or hard limit overridden."""
    quota = await _get_or_create_quota(db, job.team_id, job.season_id, job.event_id)
    open_parts, _ = await _open_usage(db, job.team_id, job.event_id)
    committed = quota.used_parts + open_parts  # includes `job` (it is pending)
    if job.quota_override:
        return (
            f"Hard limit exceeded by admin override: {committed} of {quota.max_parts} parts "
            "used or requested."
        )
    if committed > quota.soft_limit_parts:
        return (
            f"Soft limit exceeded: {committed} parts used or requested "
            f"(soft limit {quota.soft_limit_parts}, hard limit {quota.max_parts})."
        )
    return None


async def ensure_job_writable(db: AsyncSession, job: PrintJob) -> None:
    """Print jobs of an archived season/event are read-only history.

    Not part of update_print_job itself: the printer poller also goes through
    it and must keep reconciling whatever a printer reports.
    """
    await ensure_writable(db, season_id=job.season_id, event_id=job.event_id)


async def update_print_job(
    db: AsyncSession,
    job_id: str,
    *,
    quota_override: bool = False,
    acting_user_id: str | None = None,
    **kwargs,
) -> PrintJob:
    """Change a job; ``quota_override`` lets a retry exceed the hard limit (admins)."""
    job = await get_print_job(db, job_id)
    old_status = job.status
    old_grams = job.actual_grams
    old_spool_id = job.spool_id
    new_status = kwargs.get("status")
    if new_status and new_status != old_status and new_status not in JOB_TRANSITIONS[old_status]:
        raise ConflictError(f"Invalid print job transition: {old_status} -> {new_status}")
    violation = None
    if old_status not in OPEN_STATUSES and new_status in OPEN_STATUSES:
        # A retry (failed -> queued) reopens the job: it counts toward the
        # hard limit again and is checked like a new submission.
        violation = await _reopen_violation(db, job)
        if violation and not quota_override:
            raise ConflictError(violation)
    if kwargs.get("spool_id"):
        await get_spool(db, kwargs["spool_id"])
    if kwargs.get("printer_id"):
        await get_printer(db, kwargs["printer_id"])

    for key, value in kwargs.items():
        if value is not None:
            setattr(job, key, value)

    now = datetime.now(UTC)
    if new_status and new_status != old_status:
        if new_status == "printing":
            job.started_at = now
            job.error_message = None
        elif new_status == "completed":
            job.completed_at = now
            job.progress = 100.0
            job.remaining_seconds = 0
        elif new_status == "queued":
            # A retry after a failure starts with a clean slate.
            job.error_message = None
            job.progress = None
            job.remaining_seconds = None

    await _account_filament(db, job, old_status, old_grams, old_spool_id)

    if violation:
        job.quota_override = True
        await log_action(
            db,
            "printing.quota_override",
            user_id=acting_user_id,
            resource_type="print_job",
            resource_id=job.id,
            detail={"team_id": job.team_id, "event_id": job.event_id, "reason": violation},
        )

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
    await ensure_job_writable(db, job)
    if "approved" not in JOB_TRANSITIONS[job.status]:
        raise ConflictError(f"Print job cannot be approved from {job.status}")
    await update_print_job(db, job.id, status="approved")
    job.approved_by = approved_by
    job.approved_at = datetime.now(UTC)
    return job


async def reject_print_job(db: AsyncSession, job_id: str, reason: str) -> PrintJob:
    job = await get_print_job(db, job_id)
    await ensure_job_writable(db, job)
    if "rejected" not in JOB_TRANSITIONS[job.status]:
        raise ConflictError(f"Print job cannot be rejected from {job.status}")
    job.rejection_reason = reason.strip()
    return await update_print_job(db, job.id, status="rejected")


async def stop_on_printer(db: AsyncSession, job: PrintJob, user_id: str | None) -> dict:
    """Abort a running job on its printer (OctoPrint cancel, Bambu MQTT stop).

    Returns ``{"printer_cancel": "sent" | "failed" | "not_applicable",
    "printer_message": …}``. A failure is reported, not raised: the job is
    still cancelled in the database and the organizer is told to stop the
    print at the device.
    """
    if job.status != "printing" or not job.printer_id:
        return {"printer_cancel": "not_applicable", "printer_message": None}
    printer = await get_printer(db, job.printer_id)
    if printer.printer_type == "generic" or not printer.api_url:
        return {
            "printer_cancel": "not_applicable",
            "printer_message": "Manually operated printer: stop the print on the device.",
        }
    try:
        api_key = decrypt_credential(printer.api_key_encrypted) if printer.api_key_encrypted else ""
        message = await asyncio.to_thread(
            cancel_printer_job,
            printer.printer_type,
            printer.api_url,
            api_key,
            printer.device_id,
        )
        result = {"printer_cancel": "sent", "printer_message": message}
    except Exception as exc:  # noqa: BLE001 - adapters raise network and API errors alike
        logger.warning("printer_cancel_failed", printer_id=str(printer.id), error=str(exc))
        result = {
            "printer_cancel": "failed",
            "printer_message": f"Could not stop the print on {printer.name}: {exc}"[:500],
        }
    await log_action(
        db,
        "printing.printer_cancel",
        user_id=user_id,
        resource_type="print_job",
        resource_id=job.id,
        detail={"printer_id": printer.id, **result},
    )
    return result


async def cancel_print_job(
    db: AsyncSession, job_id: str, *, as_admin: bool, user_id: str | None = None
) -> tuple[PrintJob, dict]:
    """Teams may withdraw their own job while it is pending; admins any open job.

    A job that is printing is also aborted on the printer (spec: "auf Drucker
    und in Datenbank"). Returns the job and the printer's answer.
    """
    job = await get_print_job(db, job_id)
    await ensure_job_writable(db, job)
    if not as_admin and job.status != "pending":
        raise ConflictError("Only pending print jobs can be cancelled by the team")
    if "cancelled" not in JOB_TRANSITIONS[job.status]:
        raise ConflictError(f"Print job cannot be cancelled from {job.status}")
    printer_result = await stop_on_printer(db, job, user_id)
    return await update_print_job(db, job.id, status="cancelled"), printer_result


def assert_file_replaceable(job: PrintJob, *, as_admin: bool) -> None:
    """Teams may (re)upload while the job is pending; admins until it prints."""
    if as_admin:
        if job.status in ("printing", "completed", "cancelled", "rejected"):
            raise ConflictError(f"The file of a {job.status} print job cannot be changed")
    elif job.status != "pending":
        raise ConflictError("The file can only be changed while the job is pending")


def attach_file(
    job: PrintJob,
    relative_path: str,
    file_name: str,
    size: int,
    bounding_box: tuple[float, float, float] | None = None,
) -> PrintJob:
    job.file_path = relative_path
    job.file_name = file_name
    job.file_size_bytes = size
    job.file_url = f"/api/printing/jobs/{job.id}/file"
    job.bbox_x_mm, job.bbox_y_mm, job.bbox_z_mm = bounding_box or (None, None, None)
    return job


#: Jobs whose parts never reached a robot.
_NOT_PRINTED = ("rejected", "cancelled", "failed")


async def robot_parts_summary(db: AsyncSession, team_id: str, season_id: str) -> dict:
    """Robot parts a team printed or queued in a season (game review: at most 6).

    Spare copies for the judges and positioning jigs are not counted
    (``purpose``); rejected, cancelled and failed jobs neither.
    """
    from modules.printing.rules import MAX_ROBOT_PARTS

    result = await db.execute(
        select(
            func.coalesce(func.sum(PrintJob.part_count), 0),
            func.coalesce(func.sum(case((PrintJob.stl_submitted.is_(False), 1), else_=0)), 0),
        ).where(
            PrintJob.team_id == team_id,
            PrintJob.season_id == season_id,
            PrintJob.purpose == "robot",
            PrintJob.status.not_in(_NOT_PRINTED),
        )
    )
    used, stl_missing = result.one()
    return {
        "team_id": team_id,
        "season_id": season_id,
        "used": int(used or 0),
        "limit": MAX_ROBOT_PARTS,
        "over_limit": int(used or 0) > MAX_ROBOT_PARTS,
        "stl_missing": int(stl_missing or 0),
    }


# ── Quotas ────────────────────────────────────────────────────────────────────


async def _open_usage(db: AsyncSession, team_id: str, event_id: str | None) -> tuple[int, float]:
    """(number, estimated grams) of the team's unfinished jobs in the event."""
    result = await db.execute(
        select(
            func.count(PrintJob.id), func.coalesce(func.sum(PrintJob.estimated_grams), 0.0)
        ).where(
            PrintJob.team_id == team_id,
            PrintJob.event_id == event_id,
            PrintJob.status.in_(OPEN_STATUSES),
        )
    )
    count, grams = result.one()
    return int(count), float(grams or 0.0)


async def _hard_limit_violation(
    db: AsyncSession, quota: TeamSeasonPrintQuota, estimated_grams: float | None
) -> str | None:
    """Why one more job would exceed a hard limit, or None if it fits."""
    open_parts, open_grams = await _open_usage(db, quota.team_id, quota.event_id)
    committed_parts = quota.used_parts + open_parts
    if committed_parts + 1 > quota.max_parts:
        return (
            f"Hard print limit reached ({quota.max_parts} parts; {quota.used_parts} printed, "
            f"{open_parts} open). Cannot submit more jobs."
        )
    if quota.max_grams is not None and estimated_grams is not None:
        committed_grams = quota.used_grams + open_grams
        if committed_grams + estimated_grams > quota.max_grams:
            return (
                f"Filament limit reached ({quota.max_grams:g} g; {committed_grams:g} g used or "
                f"requested, this job needs {estimated_grams:g} g)."
            )
    return None


async def _locked_quota(
    db: AsyncSession, team_id: str, season_id: str, event_id: str | None
) -> TeamSeasonPrintQuota:
    """The team's quota row, locked until the transaction ends (PostgreSQL).

    Every hard-limit check runs under this lock, so two concurrent
    submissions (a double click, two mentors) are checked one after the
    other and the second one sees the first one's job.
    """
    quota = await _get_or_create_quota(db, team_id, season_id, event_id)
    locked = await db.execute(
        select(TeamSeasonPrintQuota)
        .where(TeamSeasonPrintQuota.id == quota.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return locked.scalar_one()


async def _reopen_violation(db: AsyncSession, job: PrintJob) -> str | None:
    """Why reopening ``job`` would exceed a hard limit (it is not counted as open yet)."""
    quota = await _locked_quota(db, job.team_id, job.season_id, job.event_id)
    return await _hard_limit_violation(db, quota, job.estimated_grams)


async def _get_or_create_quota(
    db: AsyncSession, team_id: str, season_id: str, event_id: str | None = None
) -> TeamSeasonPrintQuota:
    """The team's quota row for one event (the season's default event if omitted).

    Quotas are always looked up by (event, team) – the unique key. A season-only
    lookup matched one row per event and failed with MultipleResultsFound as
    soon as a season had a second event.
    """
    if event_id is None:
        event_id = (await get_default_event(db, season_id)).id

    def _existing():
        return select(TeamSeasonPrintQuota).where(
            TeamSeasonPrintQuota.team_id == team_id,
            TeamSeasonPrintQuota.event_id == event_id,
        )

    quota = (await db.execute(_existing())).scalar_one_or_none()
    if quota:
        return quota

    # Two requests can reach this point concurrently. Insert inside a savepoint
    # so a lost race only rolls back the insert (not the caller's transaction),
    # then read the winner's row — uq_print_quota_event_team makes the loser fail.
    try:
        async with db.begin_nested():
            quota = TeamSeasonPrintQuota(team_id=team_id, season_id=season_id, event_id=event_id)
            db.add(quota)
            await db.flush()
        return quota
    except IntegrityError:
        return (await db.execute(_existing())).scalar_one()


async def _account_filament(
    db: AsyncSession,
    job: PrintJob,
    old_status: str,
    old_grams: float | None,
    old_spool_id: str | None,
) -> None:
    """Book a completed job's part and filament on the quota and its spool.

    Runs on every update so grams entered (or corrected) after the job was
    completed – e.g. auto-completed by the printer poller – are booked as the
    difference to what was booked before, never twice.
    """
    if job.status != "completed":
        return
    was_booked = old_status == "completed"
    booked_grams = (old_grams or 0.0) if was_booked else 0.0
    booked_spool = old_spool_id if was_booked else None
    new_grams = job.actual_grams or 0.0

    quota = await _get_or_create_quota(db, job.team_id, job.season_id, job.event_id)
    if not was_booked:
        quota.used_parts += 1
    quota.used_grams = max(0.0, quota.used_grams + new_grams - booked_grams)

    if booked_spool and booked_spool != job.spool_id:
        await _adjust_spool(db, booked_spool, booked_grams)  # give it back
        booked_grams = 0.0
    if job.spool_id:
        await _adjust_spool(db, job.spool_id, booked_grams - new_grams)


async def quota_summary(db: AsyncSession, quota: TeamSeasonPrintQuota) -> dict:
    """Quota row plus the team's open (not yet finished) jobs."""
    open_parts, open_grams = await _open_usage(db, quota.team_id, quota.event_id)
    return {
        "id": quota.id,
        "team_id": quota.team_id,
        "season_id": quota.season_id,
        "event_id": quota.event_id,
        "max_parts": quota.max_parts,
        "soft_limit_parts": quota.soft_limit_parts,
        "max_grams": quota.max_grams,
        "used_parts": quota.used_parts,
        "used_grams": quota.used_grams,
        "open_parts": open_parts,
        "open_grams": open_grams,
        "notes": quota.notes,
    }


async def get_quota(
    db: AsyncSession, team_id: str, season_id: str, event_id: str | None = None
) -> TeamSeasonPrintQuota:
    event = await resolve_event(db, season_id, event_id)
    return await _get_or_create_quota(db, team_id, season_id, event.id)


async def list_event_quotas(db: AsyncSession, event_id: str) -> list[dict]:
    """Quota summaries of every team registered for the event (for the admin UI)."""
    from modules.events.models import Event, EventRegistration
    from modules.teams.models import Team

    event = await db.get(Event, event_id)
    if not event:
        raise NotFoundError("Event not found")
    teams = (
        await db.execute(
            select(Team.id, Team.name)
            .join(EventRegistration, EventRegistration.team_id == Team.id)
            .where(EventRegistration.event_id == event_id)
            .order_by(Team.name)
        )
    ).all()
    summaries = []
    for team_id, team_name in teams:
        quota = await _get_or_create_quota(db, team_id, event.season_id, event.id)
        summaries.append({**await quota_summary(db, quota), "team_name": team_name})
    return summaries


async def apply_printer_status(db: AsyncSession, printer: Printer, status) -> None:
    """Store a polled printer status and move the job it concerns along.

    Only a job that is actually ``printing`` on this printer can complete or
    fail. A freshly ``queued`` job is only picked up once the printer reports
    it is printing: Bambu printers keep reporting FINISH for the previous print
    until a new one starts, which used to complete every newly queued job.
    """
    now = datetime.now(UTC)
    printer.is_online = status.online
    printer.last_seen = now if status.online else printer.last_seen
    printer.current_state = status.state
    printer.status_message = (status.error or status.message or "")[:500] or None
    if not status.online:
        return

    async def _first(job_status: str, order) -> PrintJob | None:
        result = await db.execute(
            select(PrintJob)
            .where(PrintJob.printer_id == printer.id, PrintJob.status == job_status)
            .order_by(order)
        )
        return result.scalars().first()

    job = await _first("printing", PrintJob.started_at)
    if job is None:
        if status.state != "printing":
            return
        job = await _first("queued", PrintJob.priority.desc())
        if job is None:
            return

    job.last_polled_at = now
    job.status_message = (status.message or "")[:500] or None
    if status.progress is not None:
        job.progress = status.progress
    job.remaining_seconds = status.remaining_seconds

    if status.state == "printing" and job.status == "queued":
        await update_print_job(db, job.id, status="printing")
    elif job.status != "printing":
        return
    elif status.state == "completed":
        await update_print_job(db, job.id, status="completed")
    elif status.state == "failed":
        job.error_message = status.error or status.message or "Print failed"
        await update_print_job(db, job.id, status="failed")
    elif status.state == "idle":
        # The printer is idle again although we saw this job printing.
        if status.progress is None or status.progress >= _DONE_PROGRESS:
            await update_print_job(db, job.id, status="completed")
        else:
            job.error_message = "Print stopped on the printer before it finished"
            await update_print_job(db, job.id, status="failed")
    elif status.error:
        job.error_message = status.error


async def set_quota(
    db: AsyncSession,
    team_id: str,
    season_id: str,
    event_id: str | None = None,
    *,
    clear_max_grams: bool = False,
    **kwargs,
) -> TeamSeasonPrintQuota:
    event = await resolve_event(db, season_id, event_id)
    await ensure_writable(db, season_id=season_id, event_id=event.id)
    quota = await _get_or_create_quota(db, team_id, season_id, event.id)
    for key, value in kwargs.items():
        if value is not None:
            setattr(quota, key, value)
    if clear_max_grams:
        quota.max_grams = None
    await db.flush()
    return quota


# ── Filament spools ───────────────────────────────────────────────────────────


async def list_spools(db: AsyncSession, printer_id: str | None = None) -> list[FilamentSpool]:
    q = select(FilamentSpool).where(FilamentSpool.is_active == True)
    if printer_id:
        q = q.where(FilamentSpool.printer_id == printer_id)
    result = await db.execute(q)
    return list(result.scalars().all())


async def get_spool(db: AsyncSession, spool_id: str) -> FilamentSpool:
    spool = await db.get(FilamentSpool, spool_id)
    if not spool:
        raise NotFoundError("Filament spool not found")
    return spool


async def create_spool(db: AsyncSession, data: dict) -> FilamentSpool:
    # A fresh spool's remaining filament equals its initial amount unless
    # explicitly overridden. Do not mutate the caller's request dictionary.
    spool_data = data.copy()
    spool_data.setdefault("remaining_grams", spool_data.get("initial_grams", 1000.0))
    spool = FilamentSpool(**spool_data)
    db.add(spool)
    await db.flush()
    return spool


async def _adjust_spool(db: AsyncSession, spool_id: str, delta: float) -> None:
    """Add `delta` grams (negative = consume), clamped to [0, initial_grams]."""
    if not delta:
        return
    spool = await db.get(FilamentSpool, spool_id)
    if spool is None:  # deleted meanwhile (FK is SET NULL)
        return
    spool.remaining_grams = min(spool.initial_grams, max(0.0, spool.remaining_grams + delta))


async def consume_filament(db: AsyncSession, spool_id: str, grams: float) -> FilamentSpool:
    spool = await get_spool(db, spool_id)
    spool.remaining_grams = max(0.0, spool.remaining_grams - grams)
    return spool
