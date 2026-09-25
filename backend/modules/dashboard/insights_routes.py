"""Analytics, role summary and deadline calendar routes (mounted under /dashboard).

Scoping:
- Performance data of a single team: the team's own members, or organizers
  holding ``scoring:admin``. ``scoring:read`` alone is not enough — every
  mentor and guest holds it, and practice runs are internal to a team.
- Event statistics and anomaly detection: ``scoring:admin`` (jurors, admins);
  they exist to double-check other people's entries.
- History: ``teams:read`` for official results; practice figures only for the
  team itself and organizers.
"""

from datetime import date

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import (
    assert_team_access,
    bearer_scheme,
    get_current_user,
    has_elevated_access,
    own_team_ids,
    require_permission,
)
from core.database import get_db
from core.exceptions import UnauthorizedError
from modules.dashboard import analytics, calendar
from modules.dashboard.schemas import (
    CalendarFeedCreated,
    CalendarFeedStatus,
    DashboardSummary,
    DeadlineEntry,
    EventStatistics,
    PerformanceOverviewRow,
    SeasonTimeline,
    TeamHistoryRow,
    TeamPerformance,
)
from modules.dashboard.summary import build_summary
from modules.seasons.service import get_season

router = APIRouter()

TEAM_ELEVATED = "scoring:admin"


# ── Role summary ──────────────────────────────────────────────────────────────


@router.get("/summary", response_model=DashboardSummary)
async def get_summary(
    event_id: str = Query(...),
    current_user=Depends(require_permission("dashboard:read")),
    db: AsyncSession = Depends(get_db),
):
    """Role-aware overview: juror queue, own team status, organizer progress."""
    return await build_summary(db, current_user, event_id)


# ── Team history & performance ────────────────────────────────────────────────


async def _may_see_practice(db: AsyncSession, user, team_id: str) -> bool:
    if await has_elevated_access(db, user, TEAM_ELEVATED):
        return True
    return team_id in await own_team_ids(db, user)


@router.get("/teams/{team_id}/history", response_model=list[TeamHistoryRow])
async def get_team_history(
    team_id: str,
    current_user=Depends(require_permission("teams:read")),
    db: AsyncSession = Depends(get_db),
):
    """Results of a team at every event over all seasons, oldest first."""
    include_practice = await _may_see_practice(db, current_user, team_id)
    return await analytics.team_history(db, team_id, include_practice=include_practice)


@router.get("/events/{event_id}/performance", response_model=list[PerformanceOverviewRow])
async def get_performance_overview(
    event_id: str,
    current_user=Depends(require_permission("scoring:read")),
    db: AsyncSession = Depends(get_db),
):
    """Team comparison: all teams for organizers, the own teams for mentors."""
    scope = (
        None
        if await has_elevated_access(db, current_user, TEAM_ELEVATED)
        else await own_team_ids(db, current_user)
    )
    return await analytics.performance_overview(db, event_id, scope)


@router.get("/events/{event_id}/teams/{team_id}/performance", response_model=TeamPerformance)
async def get_team_performance(
    event_id: str,
    team_id: str,
    include_practice: bool = Query(True),
    current_user=Depends(require_permission("scoring:read")),
    db: AsyncSession = Depends(get_db),
):
    await assert_team_access(db, current_user, team_id, TEAM_ELEVATED)
    return await analytics.team_performance(db, event_id, team_id, include_practice)


@router.get("/events/{event_id}/statistics", response_model=EventStatistics)
async def get_event_statistics(
    event_id: str,
    include_practice: bool = Query(False),
    _=Depends(require_permission("scoring:admin")),
    db: AsyncSession = Depends(get_db),
):
    """Distributions, heatmap, trends and flagged runs for jurors to double-check."""
    return await analytics.event_statistics(db, event_id, include_practice)


# ── Deadlines ─────────────────────────────────────────────────────────────────


@router.get("/deadlines", response_model=list[DeadlineEntry])
async def list_deadlines(
    season_id: str | None = Query(None),
    since: date | None = Query(None),
    current_user=Depends(require_permission("seasons:read")),
    db: AsyncSession = Depends(get_db),
):
    """Deadlines of one season, or of every season that concerns the caller."""
    if season_id:
        await get_season(db, season_id)
        season_ids = {season_id}
    else:
        season_ids = await calendar.relevant_season_ids(db, current_user)
    return await calendar.collect_deadlines(db, current_user, season_ids, since=since)


@router.get("/seasons/{season_id}/timeline", response_model=SeasonTimeline)
async def get_season_timeline(
    season_id: str,
    current_user=Depends(require_permission("seasons:read")),
    db: AsyncSession = Depends(get_db),
):
    season = await get_season(db, season_id)
    return await calendar.season_timeline(db, current_user, season)


@router.get("/calendar-feed", response_model=CalendarFeedStatus)
async def get_calendar_feed(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    record = await calendar.get_feed_token(db, current_user.id)
    if not record:
        return CalendarFeedStatus(active=False)
    return CalendarFeedStatus(
        active=True, created_at=record.created_at, last_used_at=record.last_used_at
    )


@router.post("/calendar-feed", response_model=CalendarFeedCreated, status_code=201)
async def create_calendar_feed(
    current_user=Depends(require_permission("seasons:read")),
    db: AsyncSession = Depends(get_db),
):
    """Create or rotate the caller's feed token. It is only shown this once."""
    token = await calendar.rotate_feed_token(db, current_user.id)
    return CalendarFeedCreated(token=token, path=f"/api/dashboard/deadlines.ics?token={token}")


@router.delete("/calendar-feed", status_code=204)
async def delete_calendar_feed(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await calendar.revoke_feed_token(db, current_user.id)


@router.get("/deadlines.ics", response_class=Response)
async def deadlines_ics(
    token: str | None = Query(None, description="Personal calendar feed token"),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
):
    """iCal feed of the caller's deadlines.

    Calendar apps authenticate with the personal ``token`` from
    POST /dashboard/calendar-feed; the web app may use its bearer token
    instead. The feed carries the same deadlines as GET /dashboard/deadlines.
    """
    user = None
    if token:
        user = await calendar.user_for_feed_token(db, token)
    elif credentials:
        user = await get_current_user(credentials, db)
    if user is None:
        raise UnauthorizedError("Invalid or missing calendar token")
    if not await has_elevated_access(db, user, "seasons:read"):
        raise UnauthorizedError("Invalid or missing calendar token")
    season_ids = await calendar.relevant_season_ids(db, user)
    entries = await calendar.collect_deadlines(db, user, season_ids)
    return Response(
        content=calendar.render_ics(entries),
        media_type="text/calendar; charset=utf-8",
        headers={
            "Content-Disposition": 'inline; filename="botball-deadlines.ics"',
            # The URL is a credential; keep it out of shared caches.
            "Cache-Control": "private, max-age=300",
        },
    )
