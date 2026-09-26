from typing import Literal

from fastapi import APIRouter, Depends, Query, Request, Response, WebSocket
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.auth import assert_team_access, has_elevated_access, require_permission
from core.cache import Payload, cached_payload, conditional_response, dump_json
from core.database import get_db, get_session_factory
from core.domain_events import emit_event
from core.live import publish_after_commit, stream_live_events
from modules.events import live_socket, service
from modules.events.module_access import MODULE_KEYS, SEASON_FLAGS, effective_modules
from modules.events.schemas import (
    AllianceStanding,
    BracketPhaseResponse,
    BracketWeightsUpdate,
    EventCreate,
    EventModulesResponse,
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
    MatchResultRequest,
    PublicAnnouncementResponse,
    PublicRankingResponse,
    PublicResultResponse,
    ScheduledMatchResponse,
    ScheduledMatchUpdate,
    ScheduleGenerateRequest,
    ScoringSchemaResponse,
    ScoringSchemaVersionCreate,
    SeedAssignmentRequest,
)
from modules.scoring import service as scoring_service
from modules.scoring import visibility as scoring_visibility
from modules.scoring.schemas import MatchListItem, MatchResponse, RankingResponse
from modules.seasons.models import Season
from modules.teams.models import Team

router = APIRouter(prefix="/v1/events", tags=["events"])
public_router = APIRouter(prefix="/v1/public/events", tags=["public-events"])


@router.get("", response_model=list[EventResponse])
async def list_events(
    season_id: str | None = Query(None),
    status: str | None = Query(None),
    current_user=Depends(require_permission("events:read")),
    db: AsyncSession = Depends(get_db),
):
    return await service.list_events(
        db,
        season_id,
        status,
        include_drafts=await has_elevated_access(db, current_user, "events:write"),
    )


@router.websocket("/{event_id}/ws")
async def event_ws(
    event_id: str,
    websocket: WebSocket,
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
):
    """Live updates of any event the user may read (see modules.events.live_socket).

    The access token comes in the first message, not in the URL. Like the
    public stream, no request session is held while the socket is open.
    """
    await live_socket.serve_event_stream(websocket, event_id, session_factory)


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
    current_user=Depends(require_permission("events:read")),
    db: AsyncSession = Depends(get_db),
):
    return await service.get_event(
        db,
        event_id,
        include_drafts=await has_elevated_access(db, current_user, "events:write"),
    )


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


@router.get("/{event_id}/modules", response_model=EventModulesResponse)
async def get_event_modules(
    event_id: str,
    _=Depends(require_permission("events:read")),
    db: AsyncSession = Depends(get_db),
):
    """Which modules the event uses — drives the navigation and route guards."""
    event = await service.get_event(db, event_id)
    season = await db.get(Season, event.season_id)
    flags = (*SEASON_FLAGS.values(), "use_paper_scoring")
    return EventModulesResponse(
        event_id=event.id,
        available_modules=list(MODULE_KEYS),
        active_modules=list(event.active_modules or []),
        effective_modules=effective_modules(event, season),
        season_flags={flag: bool(getattr(season, flag, False)) for flag in flags},
    )


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
    # Live screens refresh right after the commit; the outbox row only carries
    # the push notification (publishing it live as well would be a duplicate).
    publish_after_commit(db, event_id, "schedule_updated")
    await emit_event(
        db,
        "schedule_updated",
        event_id=event_id,
        payload={"message": "The event schedule was regenerated.", "broadcast": True},
    )
    return schedule


@router.post(
    "/{event_id}/registrations/seeds-from-seeding", response_model=list[EventRegistrationResponse]
)
async def assign_seeds_from_seeding(
    event_id: str,
    body: SeedAssignmentRequest,
    _=Depends(require_permission("events:admin")),
    db: AsyncSession = Depends(get_db),
):
    """Fill the registration seeds (per category) from the seeding ranking."""
    return await service.assign_seeds_from_seeding(db, event_id, body.category, body.phase_id)


@router.post("/{event_id}/schedule/{match_id}/result", response_model=ScheduledMatchResponse)
async def record_match_result(
    event_id: str,
    match_id: str,
    body: MatchResultRequest,
    _=Depends(require_permission("scoring:admin")),
    db: AsyncSession = Depends(get_db),
):
    """Record a match result; elimination winners and losers advance automatically."""
    match = await service.record_match_result(db, event_id, match_id, body.model_dump())
    publish_after_commit(db, event_id, "schedule_updated", {"matchId": match.id})
    publish_after_commit(db, event_id, "ranking_updated")
    return match


@router.get("/{event_id}/bracket", response_model=list[BracketPhaseResponse])
async def get_bracket(
    event_id: str,
    _=Depends(require_permission("events:read")),
    db: AsyncSession = Depends(get_db),
):
    return await service.get_brackets(db, event_id)


@router.get("/{event_id}/phases/{phase_id}/alliances", response_model=list[AllianceStanding])
async def get_alliance_standings(
    event_id: str,
    phase_id: str,
    _=Depends(require_permission("events:read")),
    db: AsyncSession = Depends(get_db),
):
    return await service.alliance_standings(db, event_id, phase_id)


@router.get("/{event_id}/bracket-weights", response_model=dict[str, float])
async def get_bracket_weights(
    event_id: str,
    category: str = Query("botball"),
    _=Depends(require_permission("events:read")),
    db: AsyncSession = Depends(get_db),
):
    return await service.get_bracket_weights(db, event_id, category)


@router.put("/{event_id}/bracket-weights", response_model=dict[str, float])
async def set_bracket_weights(
    event_id: str,
    body: BracketWeightsUpdate,
    category: str = Query("botball"),
    _=Depends(require_permission("events:admin")),
    db: AsyncSession = Depends(get_db),
):
    weights = await service.set_bracket_weights(db, event_id, category, body.weights)
    publish_after_commit(db, event_id, "ranking_updated")
    return weights


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
    publish_after_commit(db, event_id, "schedule_updated", {"matchId": match.id})
    team_ids = [p.team_id for p in match.participants if p.team_id]
    from modules.events.notifications import team_member_user_ids

    user_ids = await team_member_user_ids(db, team_ids)
    if user_ids:
        # Only the teams playing this match need to hear about its new slot.
        await emit_event(
            db,
            "schedule_updated",
            event_id=event_id,
            payload={
                "matchId": match.id,
                "title": f"Match {match.code} changed",
                "message": "A match of your team was rescheduled.",
                "userIds": user_ids,
            },
        )
    return match


@router.get("/{event_id}/matches", response_model=list[MatchListItem])
async def list_event_scores(
    event_id: str,
    team_id: str | None = Query(None),
    phase_id: str | None = Query(None),
    limit: int | None = Query(None, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    current_user=Depends(require_permission("scoring:read")),
    db: AsyncSession = Depends(get_db),
):
    """Scores of an event (without schema snapshots); `limit`/`offset` page.

    Foreign practice runs and notes are hidden unless the caller has
    scoring:admin (modules.scoring.visibility).
    """
    scope = await scoring_visibility.team_scope(db, current_user)
    matches = await scoring_service.list_matches(
        db,
        event_id=event_id,
        team_id=team_id,
        phase_id=phase_id,
        team_scope=scope,
        limit=limit,
        offset=offset,
    )
    return [scoring_visibility.match_list_item(match, scope) for match in matches]


@router.post("/{event_id}/matches", response_model=MatchResponse, status_code=201)
async def create_event_score(
    event_id: str,
    body: EventScoreCreate,
    current_user=Depends(require_permission("scoring:write")),
    db: AsyncSession = Depends(get_db),
):
    # Mentors hold scoring:write for self-service (migration 0014); without this
    # they could enter scores for any team. Organizers/jurors hold scoring:admin.
    await assert_team_access(db, current_user, body.team_id, "scoring:admin")
    event = await service.get_event(db, event_id)
    data = body.model_dump()
    data.update({"event_id": event.id, "season_id": event.season_id})
    match = await scoring_service.create_match(db, data, current_user.id)
    if match.scheduled_match_id:
        # A head-to-head score records the scheduled match's result as well.
        publish_after_commit(
            db, event_id, "schedule_updated", {"matchId": match.scheduled_match_id}
        )
    publish_after_commit(db, event_id, "ranking_updated", {"matchId": match.id})
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
        body.definition.to_dict() if body.definition else None,
    )


@public_router.get("/{slug}", response_model=EventPublicResponse)
async def get_public_event(slug: str, db: AsyncSession = Depends(get_db)):
    event = await service.get_public_event(db, slug)
    return EventPublicResponse.model_validate(event, from_attributes=True)


@public_router.get("/{slug}/schedule", response_model=list[ScheduledMatchResponse])
async def get_public_schedule(
    slug: str,
    request: Request,
    upcoming: bool = Query(False, description="Only matches not completed or cancelled yet"),
    limit: int | None = Query(None, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    event = await service.get_public_event(db, slug)
    if not event.public_schedule:
        from core.exceptions import NotFoundError

        raise NotFoundError("Public schedule is disabled")
    matches = await service.list_scheduled_matches(
        db, event.id, upcoming=upcoming, limit=limit, offset=offset
    )
    body = dump_json(list[ScheduledMatchResponse], matches)
    return conditional_response(request, Payload.of(body), public=True)


@public_router.get("/{slug}/bracket", response_model=list[BracketPhaseResponse])
async def get_public_bracket(slug: str, db: AsyncSession = Depends(get_db)):
    event = await service.get_public_event(db, slug)
    if not event.public_schedule:
        from core.exceptions import NotFoundError

        raise NotFoundError("Public schedule is disabled")
    return await service.get_brackets(db, event.id)


@public_router.get("/{slug}/ranking", response_model=list[PublicRankingResponse])
async def get_public_ranking(slug: str, request: Request, db: AsyncSession = Depends(get_db)):
    event = await service.get_public_event(db, slug)
    if not event.public_scoreboard:
        from core.exceptions import NotFoundError

        raise NotFoundError("Public scoreboard is disabled")

    async def compute() -> bytes:
        ranking = await scoring_service.get_ranking(db, event_id=event.id)
        team_ids = [entry.team_id for entry in ranking]
        teams_result = await db.execute(select(Team).where(Team.id.in_(team_ids)))
        teams = {team.id: team for team in teams_result.scalars().all()}
        rows = [
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
        return dump_json(list[PublicRankingResponse], rows)

    payload = await cached_payload("public-ranking", event.id, "", compute)
    return conditional_response(request, payload, public=True)


@public_router.get("/{slug}/results", response_model=list[PublicResultResponse])
async def get_public_results(
    slug: str,
    request: Request,
    limit: int | None = Query(None, ge=1, le=1000),
    # Bounded like `limit`: every distinct value is a cache entry.
    offset: int = Query(0, ge=0, le=100_000),
    order: Literal["asc", "desc"] = Query(
        "asc", description="asc: by round, then entry time; desc: the newest first"
    ),
    db: AsyncSession = Depends(get_db),
):
    event = await service.get_public_event(db, slug)
    if not event.public_results:
        from core.exceptions import NotFoundError

        raise NotFoundError("Public detailed results are disabled")

    async def compute() -> bytes:
        # Practice runs are internal preparation, not tournament results.
        matches = await scoring_service.list_matches(
            db,
            event_id=event.id,
            is_practice=False,
            limit=limit,
            offset=offset,
            newest_first=order == "desc",
        )
        team_ids = [match.team_id for match in matches]
        teams_result = await db.execute(
            select(Team.id, Team.name, Team.team_number).where(Team.id.in_(team_ids))
        )
        teams = {row.id: row for row in teams_result}
        rows = [
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
        return dump_json(list[PublicResultResponse], rows)

    params = f"{limit}:{offset}:{order}"
    payload = await cached_payload("public-results", event.id, params, compute)
    return conditional_response(request, payload, public=True)


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
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
):
    # The stream stays open for as long as the screen shows it. A request
    # session (Depends(get_db)) would hold its pool connection all that time,
    # so a few dozen screens exhausted the pool; the event is loaded in a
    # session of its own that is closed before streaming starts.
    async with session_factory() as db:
        event = await service.get_public_event(db, slug)
        event_id = event.id
        is_public = (
            event.public_scoreboard
            or event.public_schedule
            or event.public_results
            or event.public_announcements
        )
    if not is_public:
        # Nothing about this event is public, so neither is its live stream.
        await websocket.close(code=1008)
        return
    await stream_live_events(websocket, event_id)
