from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import get_current_user, permissions_of, require_permission
from core.database import get_db
from core.domain_events import emit_event
from core.exceptions import ForbiddenError, NotFoundError
from core.live import publish_after_commit
from modules.dashboard import notifications as notification_center
from modules.dashboard.insights_routes import router as insights_router
from modules.dashboard.models import Announcement

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


class AnnouncementCreate(BaseModel):
    season_id: str | None = None
    event_id: str | None = None
    title: str
    body: str
    audience: str = "all"
    expires_at: datetime | None = None


class AnnouncementResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    season_id: str | None
    event_id: str | None
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
    event_id: str | None = Query(None),
    include_unpublished: bool = Query(False),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = select(Announcement).order_by(Announcement.created_at.desc())
    if include_unpublished:
        # Drafts are internal — only those who may publish may read them.
        if not current_user.is_superuser and "dashboard:write" not in permissions_of(current_user):
            raise ForbiddenError("Missing permissions: dashboard:write")
    else:
        q = q.where(Announcement.is_published.is_(True))
    if season_id:
        q = q.where(Announcement.season_id == season_id)
    if event_id:
        q = q.where(Announcement.event_id == event_id)
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
    ann = await _get_announcement(db, ann_id)
    ann.is_published = True
    ann.published_at = datetime.now(UTC)
    # Only announcements meant for everyone go to the public live stream and
    # to every push subscriber; audience-restricted ones stay on the
    # authenticated dashboard. The live update goes out right after the
    # commit, the outbox row carries the push.
    if ann.audience == "all":
        publish_after_commit(db, ann.event_id, "announcement_published", {"announcementId": ann.id})
    await emit_event(
        db,
        "announcement_published",
        event_id=ann.event_id,
        payload={
            "title": ann.title,
            "body": ann.body,
            "announcementId": ann.id,
            "broadcast": ann.audience == "all",
        },
    )
    return ann


@router.put("/announcements/{ann_id}/unpublish", response_model=AnnouncementResponse)
async def unpublish_announcement(
    ann_id: str,
    _=Depends(require_permission("dashboard:write")),
    db: AsyncSession = Depends(get_db),
):
    ann = await _get_announcement(db, ann_id)
    was_public = ann.is_published and ann.audience == "all"
    ann.is_published = False
    if was_public:
        publish_after_commit(db, ann.event_id, "announcement_removed", {"announcementId": ann.id})
    return ann


@router.delete("/announcements/{ann_id}", status_code=204)
async def delete_announcement(
    ann_id: str,
    _=Depends(require_permission("dashboard:write")),
    db: AsyncSession = Depends(get_db),
):
    ann = await _get_announcement(db, ann_id)
    if ann.is_published and ann.audience == "all":
        publish_after_commit(db, ann.event_id, "announcement_removed", {"announcementId": ann.id})
    await db.delete(ann)


async def _get_announcement(db: AsyncSession, ann_id: str) -> Announcement:
    result = await db.execute(select(Announcement).where(Announcement.id == ann_id))
    ann = result.scalar_one_or_none()
    if not ann:
        raise NotFoundError("Announcement not found")
    return ann


@router.get("/stats")
async def get_stats(
    season_id: str | None = Query(None),
    event_id: str | None = Query(None),
    _=Depends(require_permission("dashboard:read")),
    db: AsyncSession = Depends(get_db),
):
    """Returns aggregated stats for the dashboard overview widget."""
    from sqlalchemy import func as sqlfunc

    from modules.events.models import EventRegistration
    from modules.paper_review.models import Paper
    from modules.printing.models import PrintJob
    from modules.scoring.models import Match
    from modules.teams.models import TeamSeasonRegistration

    team_count = 0
    paper_count = 0
    print_count = 0
    match_count = 0

    if event_id:
        r = await db.execute(
            select(sqlfunc.count())
            .select_from(EventRegistration)
            .where(EventRegistration.event_id == event_id)
        )
        team_count = r.scalar() or 0
        r = await db.execute(
            select(sqlfunc.count()).select_from(Paper).where(Paper.event_id == event_id)
        )
        paper_count = r.scalar() or 0
        r = await db.execute(
            select(sqlfunc.count()).select_from(PrintJob).where(PrintJob.event_id == event_id)
        )
        print_count = r.scalar() or 0
        r = await db.execute(
            select(sqlfunc.count()).select_from(Match).where(Match.event_id == event_id)
        )
        match_count = r.scalar() or 0
    elif season_id:
        r = await db.execute(
            select(sqlfunc.count())
            .select_from(TeamSeasonRegistration)
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


# ── Notification center ───────────────────────────────────────────────────────


class NotificationItem(BaseModel):
    id: str
    event_id: str | None
    event_type: str
    category: str | None
    title: str
    body: str
    url: str | None
    created_at: datetime
    read: bool


class NotificationList(BaseModel):
    items: list[NotificationItem]
    unread: int


class NotificationReadRequest(BaseModel):
    ids: list[str] = Field(default_factory=list, max_length=500)


@router.get("/notifications", response_model=NotificationList)
async def list_notifications(
    limit: int = Query(30, ge=1, le=100),
    unread_only: bool = Query(False),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """The caller's recent notifications (in-app fallback for push)."""
    items, unread = await notification_center.list_for_user(
        db,
        current_user.id,
        limit=limit,
        unread_only=unread_only,
        language=current_user.preferred_language,
    )
    return {"items": items, "unread": unread}


@router.post("/notifications/read")
async def mark_notifications_read(
    body: NotificationReadRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return {"marked": await notification_center.mark_read(db, current_user.id, body.ids)}


@router.post("/notifications/read-all")
async def mark_all_notifications_read(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return {"marked": await notification_center.mark_all_read(db, current_user.id)}


# Analytics, role summary and deadline calendar live in their own module but
# share the /dashboard prefix. Included last so the routes above keep priority.
router.include_router(insights_router)
