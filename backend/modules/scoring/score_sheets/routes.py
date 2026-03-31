"""
Score Sheet Import – FastAPI Routes

Endpoints:
  POST   /scoring/seasons/{season_id}/score-sheets              Upload new PDF
  GET    /scoring/seasons/{season_id}/score-sheets              List all sheets
  GET    /scoring/score-sheets/{sheet_id}                       Get one sheet
  GET    /scoring/score-sheets/{sheet_id}/file                  Download PDF
  POST   /scoring/score-sheets/{sheet_id}/confirm               Confirm fields
  PUT    /scoring/score-sheets/{sheet_id}/active                Set as active
  DELETE /scoring/score-sheets/{sheet_id}                       Delete
"""

from uuid import UUID
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, BackgroundTasks, UploadFile
from fastapi.responses import FileResponse
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import require_permission, get_current_user
from core.database import get_db
from . import service, schemas

router = APIRouter(prefix="/scoring", tags=["scoring", "score-sheets"])

MAX_PDF_SIZE = 20 * 1024 * 1024  # 20 MB


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------

@router.post(
    "/seasons/{season_id}/score-sheets",
    response_model=schemas.ScoreSheetTemplateResponse,
    status_code=201,
    summary="Upload a scoring sheet PDF for a season",
)
@require_permission("scoring:admin")
async def upload_score_sheet(
    season_id: UUID,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="PDF file of the official scoring sheet"),
    label: str = Form(..., description="Display name, e.g. 'ECER 2026 Official Sheet'"),
    year: int = Form(...),
    game_theme: Optional[str] = Form(None),
    competition_level_id: Optional[UUID] = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    # Validate content type
    if file.content_type not in ("application/pdf", "application/octet-stream"):
        raise HTTPException(
            status_code=400,
            detail="Only PDF files are accepted. Received: " + (file.content_type or "unknown"),
        )

    # Check file size without reading everything into memory up front
    content = await file.read()
    if len(content) > MAX_PDF_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size is {MAX_PDF_SIZE // 1024 // 1024} MB.",
        )
    await file.seek(0)

    # Save to disk
    file_path, file_size = await service.save_upload(file, season_id)

    # Persist metadata
    template = await service.create_template(
        db=db,
        season_id=season_id,
        competition_level_id=competition_level_id,
        label=label,
        year=year,
        game_theme=game_theme,
        file_path=file_path,
        file_size=file_size,
        uploaded_by=current_user.id,
    )

    # Run OCR extraction in the background so the upload response is fast
    background_tasks.add_task(service.run_ocr_pipeline, db, template.id)

    return template


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------

@router.get(
    "/seasons/{season_id}/score-sheets",
    response_model=list[schemas.ScoreSheetTemplateListItem],
    summary="List all score sheet PDFs for a season",
)
@require_permission("scoring:read")
async def list_score_sheets(
    season_id: UUID,
    competition_level_id: Optional[UUID] = None,
    db: AsyncSession = Depends(get_db),
):
    templates = await service.list_templates(db, season_id, competition_level_id)

    # Enrich with confirmed_fields_count
    result = []
    for t in templates:
        item = schemas.ScoreSheetTemplateListItem.model_validate(t)
        item.confirmed_fields_count = (
            len(t.confirmed_fields) if t.confirmed_fields else None
        )
        result.append(item)
    return result


# ---------------------------------------------------------------------------
# Get one
# ---------------------------------------------------------------------------

@router.get(
    "/score-sheets/{sheet_id}",
    response_model=schemas.ScoreSheetTemplateResponse,
    summary="Get a single score sheet with all extracted field candidates",
)
@require_permission("scoring:read")
async def get_score_sheet(
    sheet_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    template = await service.get_template(db, sheet_id)
    if not template:
        raise HTTPException(status_code=404, detail="Score sheet not found.")
    return template


# ---------------------------------------------------------------------------
# Download PDF
# ---------------------------------------------------------------------------

@router.get(
    "/score-sheets/{sheet_id}/file",
    summary="Download the original PDF",
)
@require_permission("scoring:read")
async def download_score_sheet_pdf(
    sheet_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    template = await service.get_template(db, sheet_id)
    if not template:
        raise HTTPException(status_code=404, detail="Score sheet not found.")

    pdf_path = Path(template.file_url)
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="PDF file missing from storage.")

    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        filename=template.file_name,
    )


# ---------------------------------------------------------------------------
# Confirm fields
# ---------------------------------------------------------------------------

@router.post(
    "/score-sheets/{sheet_id}/confirm",
    response_model=schemas.ScoreSheetTemplateResponse,
    summary="Admin confirms extracted fields (optionally applies them to the scoring schema)",
)
@require_permission("scoring:admin")
async def confirm_score_sheet_fields(
    sheet_id: UUID,
    body: schemas.ConfirmFieldsRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    template = await service.get_template(db, sheet_id)
    if not template:
        raise HTTPException(status_code=404, detail="Score sheet not found.")
    if not body.fields:
        raise HTTPException(status_code=400, detail="fields list must not be empty.")

    return await service.confirm_fields(
        db=db,
        template_id=sheet_id,
        fields=body.fields,
        confirmed_by=current_user.id,
        apply_to_schema=body.apply_to_schema,
    )


# ---------------------------------------------------------------------------
# Set active
# ---------------------------------------------------------------------------

@router.put(
    "/score-sheets/{sheet_id}/active",
    status_code=204,
    summary="Mark a score sheet as the active one for its season/level",
)
@require_permission("scoring:admin")
async def set_active_score_sheet(
    sheet_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    template = await service.get_template(db, sheet_id)
    if not template:
        raise HTTPException(status_code=404, detail="Score sheet not found.")

    await service.set_active_template(
        db=db,
        season_id=template.season_id,
        competition_level_id=template.competition_level_id,
        template_id=sheet_id,
    )


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

@router.delete(
    "/score-sheets/{sheet_id}",
    status_code=204,
    summary="Delete a score sheet and its PDF file",
)
@require_permission("scoring:admin")
async def delete_score_sheet(
    sheet_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    template = await service.get_template(db, sheet_id)
    if not template:
        raise HTTPException(status_code=404, detail="Score sheet not found.")
    if template.is_active:
        raise HTTPException(
            status_code=409,
            detail="Cannot delete the active score sheet. Set another sheet as active first.",
        )
    await service.delete_template(db, sheet_id)
