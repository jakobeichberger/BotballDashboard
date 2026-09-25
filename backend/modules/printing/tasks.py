"""Periodic printer status polling executed outside API requests."""

import asyncio
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.celery_app import celery_app, run_task
from core.database import WorkerSessionLocal
from core.logging import get_logger
from modules.printing.adapters import poll_printer
from modules.printing.crypto import decrypt_credential
from modules.printing.models import Printer
from modules.printing.service import apply_printer_status

logger = get_logger(__name__)

#: Upper bound for one printer's answer. The beat polls every 15 s; a printer
#: that does not answer within this time counts as offline for this round.
POLL_TIMEOUT_SECONDS = 10.0


@dataclass(frozen=True)
class _Target:
    printer_id: str
    printer_type: str
    api_url: str
    api_key_encrypted: str
    device_id: str | None


async def _poll(target: _Target, timeout: float):
    return await asyncio.wait_for(
        asyncio.to_thread(
            poll_printer,
            target.printer_type,
            target.api_url,
            decrypt_credential(target.api_key_encrypted),
            target.device_id,
        ),
        timeout,
    )


async def poll_all_printers(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    timeout: float = POLL_TIMEOUT_SECONDS,
) -> int:
    """Poll every active printer with an adapter and store the results.

    The printers are asked concurrently (each with its own timeout), so one
    unreachable printer no longer delays all others by its full network
    timeout, and no database transaction is open while waiting for them:
    the list is read in one short transaction, the answers are written in
    another. Returns the number of printers polled.
    """
    async with session_factory() as db:
        printers = (await db.execute(select(Printer).where(Printer.is_active.is_(True)))).scalars()
        targets = [
            _Target(p.id, p.printer_type, p.api_url, p.api_key_encrypted, p.device_id)
            for p in printers
            # Generic printers are operated by hand and have no adapter.
            if p.printer_type != "generic" and p.api_url and p.api_key_encrypted
        ]
    if not targets:
        return 0

    results = await asyncio.gather(
        *(_poll(target, timeout) for target in targets), return_exceptions=True
    )

    async with session_factory() as db:
        for target, status in zip(targets, results, strict=True):
            printer = await db.get(Printer, target.printer_id)
            if printer is None:  # deleted while we were polling
                continue
            if isinstance(status, BaseException):
                logger.info("printer_poll_failed", printer_id=target.printer_id, error=str(status))
                printer.is_online = False
                printer.current_state = "offline"
                continue
            try:
                await apply_printer_status(db, printer, status)
            except Exception as exc:  # noqa: BLE001 - any failure means "offline"
                logger.warning(
                    "printer_status_failed", printer_id=target.printer_id, error=str(exc)
                )
                printer.is_online = False
                printer.current_state = "offline"
        await db.commit()
    return len(targets)


@celery_app.task(name="printing.poll_printers")
def poll_printers() -> None:
    async def run() -> None:
        await poll_all_printers(WorkerSessionLocal)

    run_task(run)
