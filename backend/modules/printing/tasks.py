"""Periodic printer status polling executed outside API requests."""

import asyncio

from sqlalchemy import select

from core.celery_app import celery_app
from core.database import AsyncSessionLocal
from core.logging import get_logger
from modules.printing.adapters import poll_printer
from modules.printing.crypto import decrypt_credential
from modules.printing.models import Printer
from modules.printing.service import apply_printer_status

logger = get_logger(__name__)


@celery_app.task(name="printing.poll_printers")
def poll_printers() -> None:
    async def run() -> None:
        async with AsyncSessionLocal() as db:
            printers = list(
                (await db.execute(select(Printer).where(Printer.is_active.is_(True)))).scalars()
            )
            for printer in printers:
                # Generic printers are operated by hand and have no adapter.
                if printer.printer_type == "generic":
                    continue
                if not printer.api_url or not printer.api_key_encrypted:
                    continue
                try:
                    status = await asyncio.to_thread(
                        poll_printer,
                        printer.printer_type,
                        printer.api_url,
                        decrypt_credential(printer.api_key_encrypted),
                        printer.device_id,
                    )
                    await apply_printer_status(db, printer, status)
                except Exception as exc:  # noqa: BLE001 - any failure means "offline"
                    logger.warning(
                        "printer_poll_failed", printer_id=str(printer.id), error=str(exc)
                    )
                    printer.is_online = False
                    printer.current_state = "offline"
            await db.commit()

    asyncio.run(run())
