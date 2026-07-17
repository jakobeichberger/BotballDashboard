from fastapi import APIRouter, Depends, Query, Response, WebSocket
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import require_permission
from core.database import get_db
from core.domain_events import emit_event
from core.live import publish_live_event, stream_live_events
from modules.events import service
from modules.events.schemas import (
    EventCreate,
    EventPhaseCreate,
    EventPhaseResponse,
    EventPhaseUpdate,
    EventPublicResponse,
    EventRegistrationCreate,
    EventRegistrationResponse,
    EventRegistrationUpdate,
    EventResponse,
    EventScoreCreate,
    EventUpdate,
    PublicAnnouncementResponse,
    PublicRankingResponse,
    PublicResultResponse,
    ScheduledMatchResponse,
    ScheduledMatchUpdate,
    ScheduleGenerateRequest,
    ScoringSchemaResponse,
    ScoringSchemaVersionCreate,
)
from modules.scoring import service as scoring_service
from modules.scoring.schemas import MatchResponse, RankingResponse
from modules.teams.models import Team

router = APIRouter(prefix="/v1/events", tags=["events"])
public_router = APIRouter(prefix="/v1/public/events", tags=["public-events"])


@router.get("", response_model=list[EventResponse])
async def list_events(
    season_id: str | None = Query(None),
    status: str | None = Query(None),
    _=Depends(require_permission("events:read")),
    db: AsyncSession = Depends(get_db),
):
    return await service.list_events(db, season_id, status)


@router.post("", response_model=EventResponse, status_code=201)
async def create_event(
    body: EventCreate,
    _=Depends(require_permission("events:write")),
    db: AsyncSession = Depends(get_db),
):
    return await service.create_event(db, body.model_dump())


@router.get("/{event_id}", response_model=EventResponse)
async def get_event(
    event_id: str,
    _=Depends(require_permission("events:read")),
    db: AsyncSession = Depends(get_db),
):
    return await service.get_event(db, event_id)


@router.patch("/{event_id}", response_model=EventResponse)
async def update_event(
    event_id: str,
    body: EventUpdate,
    _=Depends(require_permission("events:write")),
    db: AsyncSession = Depends(get_db),
):
    return await service.update_event(db, event_id, body.model_dump(exclude_unset=True))


@router.delete("/{event_id}", status_code=204)
async def delete_event(
    event_id: str,
    _=Depends(require_permission("events:admin")),
    db: AsyncSession = Depends(get_db),
):
    await service.delete_event(db, event_id)


@router.get("/{event_id}/registrations", response_model=list[EventRegistrationResponse])
async def list_registrations(
    event_id: str,
    _=Depends(require_permission("events:read")),
    db: AsyncSession = Depends(get_db),
):
    return await service.list_registrations(db, event_id)


@router.post("/{event_id}/registrations", response_model=EventRegistrationResponse, status_code=201)
async def add_registration(
    event_id: str,
    body: EventRegistrationCreate,
    _=Depends(require_permission("events:write")),
    db: AsyncSession = Depends(get_db),
):
    return await service.add_registration(db, event_id, body.model_dump())


@router.patch(
    "/{event_id}/registrations/{registration_id}",
    response_model=EventRegistrationResponse,
)
async def update_registration(
    event_id: str,
    registration_id: str,
    body: EventRegistrationUpdate,
    _=Depends(require_permission("events:write")),
    db: AsyncSession = Depends(get_db),
):
    return await service.update_registration(
        db, event_id, registration_id, body.model_dump(exclude_unset=True)
    )


@router.delete("/{event_id}/registrations/{registration_id}", status_code=204)
async def remove_registration(
    event_id: str,
    registration_id: str,
    _=Depends(require_permission("events:write")),
    db: AsyncSession = Depends(get_db),
):
    await service.remove_registration(db, event_id, registration_id)


@router.get("/{event_id}/phases", response_model=list[EventPhaseResponse])
async def list_phases(
    event_id: str,
    _=Depends(require_permission("events:read")),
    db: AsyncSession = Depends(get_db),
):
    return await service.list_phases(db, event_id)


@router.post("/{event_id}/phases", response_model=EventPhaseResponse, status_code=201)
async def create_phase(
    event_id: str,
    body: EventPhaseCreate,
    _=Depends(require_permission("events:write")),
    db: AsyncSession = Depends(get_db),
):
    return await service.create_phase(db, event_id, body.model_dump())


@router.patch("/{event_id}/phases/{phase_id}", response_model=EventPhaseResponse)
async def update_phase(
    event_id: str,
    phase_id: str,
    body: EventPhaseUpdate,
    _=Depends(require_permission("events:write")),
    db: AsyncSession = Depends(get_db),
):
    return await service.update_phase(db, event_id, phase_id, body.model_dump(exclude_unset=True))


@router.delete("/{event_id}/phases/{phase_id}", status_code=204)
async def delete_phase(
    event_id: str,
    phase_id: str,
    _=Depends(require_permission("events:write")),
    db: AsyncSession = Depends(get_db),
):
    await service.delete_phase(db, event_id, phase_id)


@router.get("/{event_id}/schedule", response_model=list[ScheduledMatchResponse])
async def list_schedule(
    event_id: str,
    phase_id: str | None = Query(None),
    _=Depends(require_permission("events:read")),
    db: AsyncSession = Depends(get_db),
):
    return await service.list_scheduled_matches(db, event_id, phase_id)


@router.post(
    "/{event_id}/schedule/generate",
    response_model=list[ScheduledMatchResponse],
    status_code=201,
)
async def generate_schedule(
    event_id: str,
    body: ScheduleGenerateRequest,
    _=Depends(require_permission("events:admin")),
    db: AsyncSession = Depends(get_db),
):
    schedule = await service.generate_schedule(db, event_id, body.model_dump())
    await publish_live_event(event_id, "schedule_updated")
    await emit_event(
        db,
        "schedule_updated",
        event_id=event_id,
        payload={"message": "The event schedule was regenerated.", "publicLive": True},
    )
    return schedule


@router.patch("/{event_id}/schedule/{match_id}", response_model=ScheduledMatchResponse)
async def update_scheduled_match(
    event_id: str,
    match_id: str,
    body: ScheduledMatchUpdate,
    _=Depends(require_permission("events:write")),
    db: AsyncSession = Depends(get_db),
):
    match = await service.update_scheduled_match(
        db, event_id, match_id, body.model_dump(exclude_unset=True)
    )
    await publish_live_event(event_id, "schedule_updated", {"matchId": match.id})
    await emit_event(
        db,
        "schedule_updated",
        event_id=event_id,
        payload={"matchId": match.id, "message": "A match time changed.", "publicLive": True},
    )
    return match


@router.get("/{event_id}/matches", response_model=list[MatchResponse])
async def list_event_scores(
    event_id: str,
    team_id: str | None = Query(None),
    phase_id: str | None = Query(None),
    _=Depends(require_permission("scoring:read")),
    db: AsyncSession = Depends(get_db),
):
    return await scoring_service.list_matches(
        db, event_id=event_id, team_id=team_id, phase_id=phase_id
    )


@router.post("/{event_id}/matches", response_model=MatchResponse, status_code=201)
async def create_event_score(
    event_id: str,
    body: EventScoreCreate,
    current_user=Depends(require_permission("scoring:write")),
    db: AsyncSession = Depends(get_db),
):
    event = await service.get_event(db, event_id)
    data = body.model_dump()
    data.update({"event_id": event.id, "season_id": event.season_id})
    match = await scoring_service.create_match(db, data, current_user.id)
    await publish_live_event(event_id, "ranking_updated", {"matchId": match.id})
    return match


@router.get("/{event_id}/ranking", response_model=list[RankingResponse])
async def get_event_ranking(
    event_id: str,
    competition_level_id: str | None = Query(None),
    phase_id: str | None = Query(None),
    _=Depends(require_permission("events:read")),
    db: AsyncSession = Depends(get_db),
):
    return await scoring_service.get_ranking(
        db,
        event_id=event_id,
        competition_level_id=competition_level_id,
        event_phase_id=phase_id,
    )


@router.get("/{event_id}/scoring-schema", response_model=ScoringSchemaResponse)
async def get_event_scoring_schema(
    event_id: str,
    competition_level_id: str | None = Query(None),
    _=Depends(require_permission("scoring:read")),
    db: AsyncSession = Depends(get_db),
):
    event = await service.get_event(db, event_id)
    schema = await scoring_service.get_active_schema(
        db, event.season_id, competition_level_id, event.id
    )
    if not schema:
        from core.exceptions import NotFoundError

        raise NotFoundError("No active scoring schema for this event")
    return schema


@router.post(
    "/{event_id}/scoring-schema/versions",
    response_model=ScoringSchemaResponse,
    status_code=201,
)
async def create_event_scoring_schema(
    event_id: str,
    body: ScoringSchemaVersionCreate,
    _=Depends(require_permission("scoring:admin")),
    db: AsyncSession = Depends(get_db),
):
    event = await service.get_event(db, event_id)
    return await scoring_service.create_schema_version(
        db,
        event,
        body.competition_level_id,
        [field.model_dump() for field in body.fields],
        body.activate,
    )


@public_router.get("/{slug}", response_model=EventPublicResponse)
async def get_public_event(slug: str, db: AsyncSession = Depends(get_db)):
    event = await service.get_public_event(db, slug)
    return EventPublicResponse.model_validate(event, from_attributes=True)


@public_router.get("/{slug}/schedule", response_model=list[ScheduledMatchResponse])
async def get_public_schedule(slug: str, db: AsyncSession = Depends(get_db)):
    event = await service.get_public_event(db, slug)
    if not event.public_schedule:
        from core.exceptions import NotFoundError

        raise NotFoundError("Public schedule is disabled")
    return await service.list_scheduled_matches(db, event.id)


@public_router.get("/{slug}/ranking", response_model=list[PublicRankingResponse])
async def get_public_ranking(slug: str, db: AsyncSession = Depends(get_db)):
    event = await service.get_public_event(db, slug)
    if not event.public_scoreboard:
        from core.exceptions import NotFoundError

        raise NotFoundError("Public scoreboard is disabled")
    ranking = await scoring_service.get_ranking(db, event_id=event.id)
    team_ids = [entry.team_id for entry in ranking]
    teams_result = await db.execute(select(Team).where(Team.id.in_(team_ids)))
    teams = {team.id: team for team in teams_result.scalars().all()}
    return [
        {
            "rank": entry.rank,
            "team_id": entry.team_id,
            "team_name": teams[entry.team_id].name,
            "team_number": teams[entry.team_id].team_number,
            "seed_score": entry.seed_score,
            "best_score": entry.best_score,
            "average_score": entry.average_score,
            "rounds_played": entry.rounds_played,
            "updated_at": entry.updated_at,
        }
        for entry in ranking
        if entry.team_id in teams
    ]


@public_router.get("/{slug}/results", response_model=list[PublicResultResponse])
async def get_public_results(slug: str, db: AsyncSession = Depends(get_db)):
    event = await service.get_public_event(db, slug)
    if not event.public_results:
        from core.exceptions import NotFoundError

        raise NotFoundError("Public detailed results are disabled")
    matches = await scoring_service.list_matches(db, event_id=event.id)
    team_ids = [match.team_id for match in matches]
    teams_result = await db.execute(select(Team).where(Team.id.in_(team_ids)))
    teams = {team.id: team for team in teams_result.scalars().all()}
    return [
        {
            "id": match.id,
            "event_id": match.event_id,
            "scheduled_match_id": match.scheduled_match_id,
            "team_id": match.team_id,
            "team_name": teams[match.team_id].name,
            "team_number": teams[match.team_id].team_number,
            "round_number": match.round_number,
            "table_number": match.table_number,
            "raw_scores": match.raw_scores,
            "total_score": match.total_score,
            "is_disqualified": match.is_disqualified,
            "yellow_card": match.yellow_card,
            "red_card": match.red_card,
            "created_at": match.created_at,
        }
        for match in matches
        if match.team_id in teams
    ]


@public_router.get("/{slug}/announcements", response_model=list[PublicAnnouncementResponse])
async def get_public_announcements(slug: str, db: AsyncSession = Depends(get_db)):
    event = await service.get_public_event(db, slug)
    if not event.public_announcements:
        from core.exceptions import NotFoundError

        raise NotFoundError("Public announcements are disabled")
    from datetime import UTC, datetime

    from modules.dashboard.models import Announcement

    result = await db.execute(
        select(Announcement)
        .where(
            Announcement.event_id == event.id,
            Announcement.is_published.is_(True),
            Announcement.audience == "all",
            (Announcement.expires_at.is_(None)) | (Announcement.expires_at > datetime.now(UTC)),
        )
        .order_by(Announcement.published_at.desc())
    )
    return list(result.scalars().all())


@public_router.get("/{slug}/qr.svg", response_class=Response)
async def get_public_qr(slug: str, db: AsyncSession = Depends(get_db)):
    event = await service.get_public_event(db, slug)
    import io

    import qrcode
    import qrcode.image.svg

    from core.config import get_settings

    public_url = f"{get_settings().app_base_url.rstrip('/')}/public/{event.slug}"
    image = qrcode.make(public_url, image_factory=qrcode.image.svg.SvgPathImage)
    output = io.BytesIO()
    image.save(output)
    return Response(content=output.getvalue(), media_type="image/svg+xml")


@public_router.websocket("/{slug}/ws")
async def public_event_ws(
    slug: str,
    websocket: WebSocket,
    db: AsyncSession = Depends(get_db),
):
    event = await service.get_public_event(db, slug)
    await stream_live_events(websocket, event.id)
