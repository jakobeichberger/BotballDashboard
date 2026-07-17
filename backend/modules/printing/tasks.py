"""Periodic printer status polling executed outside API requests."""

import asyncio

from sqlalchemy import select

from core.celery_app import celery_app
from core.database import AsyncSessionLocal
from modules.printing.adapters import poll_printer
from modules.printing.crypto import decrypt_credential
from modules.printing.models import Printer
from modules.printing.service import apply_printer_status


@celery_app.task(name="printing.poll_printers")
def poll_printers() -> None:
    async def run() -> None:
        async with AsyncSessionLocal() as db:
            printers = list(
                (await db.execute(select(Printer).where(Printer.is_active.is_(True)))).scalars()
            )
            for printer in printers:
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
                except Exception:
                    printer.is_online = False
            await db.commit()

    asyncio.run(run())
