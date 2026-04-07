from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import get_current_user, require_permission
from core.database import get_db
from modules.dashboard.models import Announcement
from pydantic import BaseModel

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


class AnnouncementCreate(BaseModel):
    season_id: str | None = None
    title: str
    body: str
    audience: str = "all"
    expires_at: datetime | None = None


class AnnouncementResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    season_id: str | None
    title: str
    body: str
    audience: str
    is_published: bool
    published_at: datetime | None
    expires_at: datetime | None
    created_at: datetime


@router.get("/announcements", response_model=list[AnnouncementResponse])
async def list_announcements(
    season_id: str | None = Query(None),
    _=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = select(Announcement).where(Announcement.is_published == True).order_by(
        Announcement.created_at.desc()
    )
    if season_id:
        q = q.where(Announcement.season_id == season_id)
    result = await db.execute(q)
    return list(result.scalars().all())


@router.post("/announcements", response_model=AnnouncementResponse, status_code=201)
async def create_announcement(
    body: AnnouncementCreate,
    current_user=Depends(require_permission("dashboard:write")),
    db: AsyncSession = Depends(get_db),
):
    ann = Announcement(**body.model_dump(), created_by=current_user.id)
    db.add(ann)
    await db.flush()
    return ann


@router.put("/announcements/{ann_id}/publish", response_model=AnnouncementResponse)
async def publish_announcement(
    ann_id: str,
    _=Depends(require_permission("dashboard:write")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Announcement).where(Announcement.id == ann_id))
    ann = result.scalar_one_or_none()
    if not ann:
        from core.exceptions import NotFoundError
        raise NotFoundError("Announcement not found")
    ann.is_published = True
    ann.published_at = datetime.now(timezone.utc)
    return ann


@router.get("/stats")
async def get_stats(
    season_id: str | None = Query(None),
    _=Depends(require_permission("dashboard:read")),
    db: AsyncSession = Depends(get_db),
):
    """Returns aggregated stats for the dashboard overview widget."""
    from sqlalchemy import func as sqlfunc
    from modules.teams.models import TeamSeasonRegistration
    from modules.paper_review.models import Paper
    from modules.printing.models import PrintJob
    from modules.scoring.models import Match

    team_count = 0
    paper_count = 0
    print_count = 0
    match_count = 0

    if season_id:
        r = await db.execute(
            select(sqlfunc.count()).select_from(TeamSeasonRegistration)
            .where(TeamSeasonRegistration.season_id == season_id)
        )
        team_count = r.scalar() or 0

        r = await db.execute(
            select(sqlfunc.count()).select_from(Paper).where(Paper.season_id == season_id)
        )
        paper_count = r.scalar() or 0

        r = await db.execute(
            select(sqlfunc.count()).select_from(PrintJob).where(PrintJob.season_id == season_id)
        )
        print_count = r.scalar() or 0

        r = await db.execute(
            select(sqlfunc.count()).select_from(Match).where(Match.season_id == season_id)
        )
        match_count = r.scalar() or 0

    return {
        "teams": team_count,
        "papers": paper_count,
        "print_jobs": print_count,
        "matches": match_count,
    }
