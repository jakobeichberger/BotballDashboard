from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import get_current_user, require_permission, require_any_permission
from core.database import get_db
from modules.paper_review import service
from modules.paper_review.schemas import (
    PaperCreate,
    PaperListItem,
    PaperResponse,
    PaperUpdate,
    ReviewCreateUpdate,
    ReviewerAssignmentCreate,
    ReviewerAssignmentResponse,
    ReviewResponse,
)

router = APIRouter(prefix="/papers", tags=["papers"])


@router.get("", response_model=list[PaperListItem])
async def list_papers(
    season_id: str | None = Query(None),
    team_id: str | None = Query(None),
    status: str | None = Query(None),
    _=Depends(require_permission("papers:read")),
    db: AsyncSession = Depends(get_db),
):
    return await service.list_papers(db, season_id, team_id, status)


@router.post("", response_model=PaperResponse, status_code=201)
async def create_paper(
    body: PaperCreate,
    _=Depends(require_permission("papers:write")),
    db: AsyncSession = Depends(get_db),
):
    return await service.create_paper(db, body.model_dump())


@router.get("/{paper_id}", response_model=PaperResponse)
async def get_paper(
    paper_id: str,
    _=Depends(require_permission("papers:read")),
    db: AsyncSession = Depends(get_db),
):
    return await service.get_paper(db, paper_id)


@router.patch("/{paper_id}", response_model=PaperResponse)
async def update_paper(
    paper_id: str,
    body: PaperUpdate,
    _=Depends(require_permission("papers:write")),
    db: AsyncSession = Depends(get_db),
):
    return await service.update_paper(db, paper_id, **body.model_dump(exclude_none=True))


@router.post("/{paper_id}/upload", response_model=PaperResponse)
async def upload_paper_file(
    paper_id: str,
    file: UploadFile = File(...),
    _=Depends(require_permission("papers:write")),
    db: AsyncSession = Depends(get_db),
):
    file_path, file_name, file_size = await service.save_file(file, paper_id)
    return await service.update_paper(
        db, paper_id,
        file_url=f"/api/papers/{paper_id}/download",
        file_name=file_name,
        file_size_bytes=file_size,
    )


@router.get("/{paper_id}/download")
async def download_paper(
    paper_id: str,
    _=Depends(require_permission("papers:read")),
    db: AsyncSession = Depends(get_db),
):
    paper = await service.get_paper(db, paper_id)
    if not paper.file_name:
        from core.exceptions import NotFoundError
        raise NotFoundError("No file uploaded")
    from core.config import get_settings as _gs
    file_path = Path(_gs().upload_dir) / "papers" / paper_id / paper.file_name
    return FileResponse(str(file_path), filename=paper.file_name, media_type="application/pdf")


@router.put("/{paper_id}/submit", response_model=PaperResponse)
async def submit_paper(
    paper_id: str,
    current_user=Depends(require_permission("papers:write")),
    db: AsyncSession = Depends(get_db),
):
    return await service.submit_paper(db, paper_id, current_user.id)


@router.put("/{paper_id}/status")
async def set_paper_status(
    paper_id: str,
    status: str = Query(...),
    _=Depends(require_permission("papers:admin")),
    db: AsyncSession = Depends(get_db),
):
    return await service.set_paper_status(db, paper_id, status)


# ── Reviewer assignments ──────────────────────────────────────────────────────

@router.post("/{paper_id}/assignments", response_model=ReviewerAssignmentResponse, status_code=201)
async def assign_reviewer(
    paper_id: str,
    body: ReviewerAssignmentCreate,
    current_user=Depends(require_permission("papers:admin")),
    db: AsyncSession = Depends(get_db),
):
    return await service.assign_reviewer(db, paper_id, body.reviewer_id, current_user.id)


# ── Reviews ───────────────────────────────────────────────────────────────────

@router.put("/{paper_id}/reviews", response_model=ReviewResponse)
async def save_review(
    paper_id: str,
    body: ReviewCreateUpdate,
    submit: bool = Query(False),
    current_user=Depends(require_permission("papers:review")),
    db: AsyncSession = Depends(get_db),
):
    return await service.save_review(
        db, paper_id, current_user.id, body.model_dump(exclude_none=True), submit=submit
    )


@router.get("/{paper_id}/reviews", response_model=list[ReviewResponse])
async def list_reviews(
    paper_id: str,
    _=Depends(require_permission("papers:admin")),
    db: AsyncSession = Depends(get_db),
):
    paper = await service.get_paper(db, paper_id)
    return paper.reviews
