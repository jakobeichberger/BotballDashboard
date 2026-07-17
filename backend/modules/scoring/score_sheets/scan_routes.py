"""Event-scoped upload and mandatory review APIs for local OCR scans."""

from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import require_permission
from core.config import get_settings
from core.database import get_db
from modules.scoring.schemas import MatchResponse
from modules.scoring.score_sheets import scan_service
from modules.scoring.score_sheets.schemas import (
    ScoreSheetScanAccept,
    ScoreSheetScanResponse,
)

router = APIRouter(prefix="/v1/events", tags=["score-sheet-scans"])

ALLOWED_SCAN_TYPES = {"application/pdf", "image/jpeg", "image/png", "image/webp"}


@router.post(
    "/{event_id}/score-sheet-scans",
    response_model=ScoreSheetScanResponse,
    status_code=202,
)
async def upload_scan(
    event_id: UUID,
    template_id: UUID = Form(...),
    team_id: UUID = Form(...),
    scheduled_match_id: UUID | None = Form(None),
    file: UploadFile = File(...),
    current_user=Depends(require_permission("scoring:write")),
    db: AsyncSession = Depends(get_db),
):
    if file.content_type not in ALLOWED_SCAN_TYPES:
        raise HTTPException(status_code=415, detail="PDF, JPEG, PNG or WebP required")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded scan is empty")
    if len(content) > get_settings().max_upload_size_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Uploaded scan exceeds the size limit")
    await file.seek(0)
    file_path, _ = await scan_service.save_scan_upload(file, str(event_id))
    scan = await scan_service.create_scan(
        db,
        event_id=str(event_id),
        template_id=str(template_id),
        team_id=str(team_id),
        scheduled_match_id=str(scheduled_match_id) if scheduled_match_id else None,
        file_path=file_path,
        created_by=current_user.id,
    )
    await db.flush()
    try:
        from modules.scoring.score_sheets.tasks import process_scan

        process_scan.delay(scan.id)
    except Exception:
        pass
    return scan


@router.get("/{event_id}/score-sheet-scans", response_model=list[ScoreSheetScanResponse])
async def list_scans(
    event_id: UUID,
    status: str | None = Query(None),
    _=Depends(require_permission("scoring:read")),
    db: AsyncSession = Depends(get_db),
):
    return await scan_service.list_scans(db, str(event_id), status)


@router.get("/{event_id}/score-sheet-scans/{scan_id}", response_model=ScoreSheetScanResponse)
async def get_scan(
    event_id: UUID,
    scan_id: UUID,
    _=Depends(require_permission("scoring:read")),
    db: AsyncSession = Depends(get_db),
):
    return await scan_service.get_scan(db, str(event_id), str(scan_id))


@router.post(
    "/{event_id}/score-sheet-scans/{scan_id}/retry",
    response_model=ScoreSheetScanResponse,
)
async def retry_scan(
    event_id: UUID,
    scan_id: UUID,
    _=Depends(require_permission("scoring:write")),
    db: AsyncSession = Depends(get_db),
):
    scan = await scan_service.get_scan(db, str(event_id), str(scan_id))
    if scan.status not in ("failed", "queued"):
        raise HTTPException(status_code=409, detail="Only queued or failed scans can be retried")
    scan.status = "queued"
    scan.error = None
    await db.flush()
    from modules.scoring.score_sheets.tasks import process_scan

    process_scan.delay(scan.id)
    return scan


@router.post(
    "/{event_id}/score-sheet-scans/{scan_id}/accept",
    response_model=MatchResponse,
)
async def accept_scan(
    event_id: UUID,
    scan_id: UUID,
    body: ScoreSheetScanAccept,
    current_user=Depends(require_permission("scoring:write")),
    db: AsyncSession = Depends(get_db),
):
    scan = await scan_service.get_scan(db, str(event_id), str(scan_id))
    return await scan_service.accept_scan(
        db,
        scan,
        body.values,
        current_user.id,
        body.correction_reason,
    )


@router.get("/{event_id}/score-sheet-scans/{scan_id}/crops/{file_name}")
async def get_scan_crop(
    event_id: UUID,
    scan_id: UUID,
    file_name: str,
    _=Depends(require_permission("scoring:read")),
    db: AsyncSession = Depends(get_db),
):
    scan = await scan_service.get_scan(db, str(event_id), str(scan_id))
    if Path(file_name).name != file_name:
        raise HTTPException(status_code=400, detail="Invalid crop name")
    path = Path(scan.file_url).parent / scan.id / "crops" / file_name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Crop not found")
    return FileResponse(path, media_type="image/png")
