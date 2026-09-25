"""Event-scoped upload and mandatory review APIs for local OCR scans."""

from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import assert_team_access, has_elevated_access, own_team_ids, require_permission
from core.config import get_settings
from core.database import get_db
from core.rate_limit import rate_limit
from core.task_queue import enqueue_after_commit
from modules.scoring.schemas import MatchResponse
from modules.scoring.score_sheets import scan_service
from modules.scoring.score_sheets.schemas import (
    ScoreSheetScanAccept,
    ScoreSheetScanResponse,
)
from modules.seasons.lifecycle import ensure_writable

router = APIRouter(prefix="/v1/events", tags=["score-sheet-scans"])

ALLOWED_SCAN_TYPES = {"application/pdf", "image/jpeg", "image/png", "image/webp"}

# Scans show a team's handwritten score sheet. Organizers and jurors
# (scoring:admin) review all of them; everyone else with scoring:read – mentors,
# guests – only sees the scans of their own teams.
_SCAN_REVIEWER = "scoring:admin"


def _queue_ocr(db: AsyncSession, scan_id: str) -> None:
    """Hand the scan to the OCR worker once its row is committed."""
    from modules.scoring.score_sheets.tasks import process_scan

    enqueue_after_commit(db, process_scan, scan_id)


@router.post(
    "/{event_id}/score-sheet-scans",
    response_model=ScoreSheetScanResponse,
    status_code=202,
    dependencies=[Depends(rate_limit("score-scan-upload", 30, 60))],
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
    # Checked before the upload is read, so an unauthorised request is not buffered.
    await assert_team_access(db, current_user, str(team_id), "scoring:admin")
    if file.content_type not in ALLOWED_SCAN_TYPES:
        raise HTTPException(status_code=415, detail="PDF, JPEG, PNG or WebP required")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded scan is empty")
    if len(content) > get_settings().max_upload_size_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Uploaded scan exceeds the size limit")
    # Validates template, team, match, season and file content before the file
    # is written.
    scan = await scan_service.create_scan(
        db,
        event_id=str(event_id),
        template_id=str(template_id),
        team_id=str(team_id),
        scheduled_match_id=str(scheduled_match_id) if scheduled_match_id else None,
        content=content,
        created_by=current_user.id,
    )
    _queue_ocr(db, scan.id)
    return scan


@router.get("/{event_id}/score-sheet-scans", response_model=list[ScoreSheetScanResponse])
async def list_scans(
    event_id: UUID,
    status: str | None = Query(None),
    current_user=Depends(require_permission("scoring:read")),
    db: AsyncSession = Depends(get_db),
):
    team_ids = None
    if not await has_elevated_access(db, current_user, _SCAN_REVIEWER):
        team_ids = await own_team_ids(db, current_user)
    return await scan_service.list_scans(db, str(event_id), status, team_ids)


@router.get("/{event_id}/score-sheet-scans/{scan_id}", response_model=ScoreSheetScanResponse)
async def get_scan(
    event_id: UUID,
    scan_id: UUID,
    current_user=Depends(require_permission("scoring:read")),
    db: AsyncSession = Depends(get_db),
):
    scan = await scan_service.get_scan(db, str(event_id), str(scan_id))
    await assert_team_access(db, current_user, scan.team_id, _SCAN_REVIEWER)
    return scan


@router.post(
    "/{event_id}/score-sheet-scans/{scan_id}/retry",
    response_model=ScoreSheetScanResponse,
)
async def retry_scan(
    event_id: UUID,
    scan_id: UUID,
    current_user=Depends(require_permission("scoring:write")),
    db: AsyncSession = Depends(get_db),
):
    scan = await scan_service.get_scan(db, str(event_id), str(scan_id))
    await assert_team_access(db, current_user, scan.team_id, _SCAN_REVIEWER)
    if scan.status not in ("failed", "queued"):
        raise HTTPException(status_code=409, detail="Only queued or failed scans can be retried")
    await ensure_writable(db, event_id=scan.event_id)
    scan.status = "queued"
    scan.error = None
    await db.flush()
    _queue_ocr(db, scan.id)
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
    # Accepting turns the scan into an official match score for scan.team_id.
    await assert_team_access(db, current_user, scan.team_id, "scoring:admin")
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
    current_user=Depends(require_permission("scoring:read")),
    db: AsyncSession = Depends(get_db),
):
    scan = await scan_service.get_scan(db, str(event_id), str(scan_id))
    await assert_team_access(db, current_user, scan.team_id, _SCAN_REVIEWER)
    if Path(file_name).name != file_name:
        raise HTTPException(status_code=400, detail="Invalid crop name")
    path = Path(scan.file_url).parent / scan.id / "crops" / file_name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Crop not found")
    return FileResponse(path, media_type="image/png")
