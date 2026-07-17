"""Celery entry points for all score-sheet OCR work."""

import asyncio
from datetime import UTC, datetime

from sqlalchemy import select

from core.celery_app import celery_app
from core.database import AsyncSessionLocal
from modules.scoring.score_sheets.models import ScoreSheetScan, ScoreSheetTemplate
from modules.scoring.score_sheets.scan_service import run_local_ocr
from modules.scoring.score_sheets.service import run_ocr_pipeline


@celery_app.task(name="score_sheets.extract_template")
def extract_template(template_id: str) -> None:
    async def run() -> None:
        async with AsyncSessionLocal() as db:
            await run_ocr_pipeline(db, template_id)

    asyncio.run(run())


@celery_app.task(name="score_sheets.process_scan")
def process_scan(scan_id: str) -> None:
    async def run() -> None:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(ScoreSheetScan).where(ScoreSheetScan.id == scan_id))
            scan = result.scalar_one_or_none()
            if not scan:
                return
            scan.status = "processing"
            await db.commit()
            try:
                template = await db.get(ScoreSheetTemplate, scan.template_id)
                if not template:
                    raise RuntimeError("Score-sheet template not found")
                scan.extracted_values = run_local_ocr(scan, template)
                scan.status = "review"
                scan.processed_at = datetime.now(UTC)
                scan.error = None
            except Exception as exc:
                scan.status = "failed"
                scan.error = str(exc)[:4000]
            await db.commit()

    asyncio.run(run())
