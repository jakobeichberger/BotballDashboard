from fastapi import APIRouter, Depends, Query, Request
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import (
    assert_team_access,
    bearer_scheme,
    get_current_user,
    has_elevated_access,
    own_team_ids,
    require_permission,
)
from core.cache import cached_payload, conditional_response, dump_json
from core.database import get_db
from core.exceptions import ForbiddenError, NotFoundError, UnauthorizedError
from core.live import publish_after_commit
from modules.events import service as event_svc
from modules.events.draft_access import DRAFT_READERS, is_draft_event
from modules.events.models import Event
from modules.events.module_access import require_season_event_module
from modules.scoring import competition_service as comp_svc
from modules.scoring import formula_service as formula_svc
from modules.scoring import service
from modules.scoring import visibility as scope_svc
from modules.scoring.competition_schemas import (
    AerialResultResponse,
    AerialResultUpsert,
    DEResultResponse,
    DEResultUpsert,
    DocScoreResponse,
    DocScoreUpsert,
    JBCResultResponse,
    JBCResultUpsert,
    OverallRankingEntry,
    ResultRevisionResponse,
    TeamRankingEntry,
)
from modules.scoring.schemas import (
    MatchConfirm,
    MatchCreate,
    MatchListItem,
    MatchResponse,
    MatchUpdate,
    RankingResponse,
    ScoreBulkEntry,
    ScoreRevisionResponse,
    ScoringSchemaResponse,
)
from modules.seasons import service as season_svc
from modules.seasons.lifecycle import DRAFT
from modules.seasons.models import Season
from modules.teams.models import Team

router = APIRouter(prefix="/scoring", tags=["scoring"])

# Results are recorded per event. Every result resource therefore exists twice:
#   /scoring/events/{event_id}/…    — the event the UI is working in
#   /scoring/seasons/{season_id}/…  — kept for older clients; it takes an
#                                     optional ?event_id= and otherwise uses the
#                                     season's default (earliest) event, for
#                                     reads, writes and the overall ranking alike.

# Competition modules switched off for the addressed event answer 404.
_DE = [Depends(require_season_event_module("double_elimination"))]
_AERIAL = [Depends(require_season_event_module("aerial"))]
_DOC = [Depends(require_season_event_module("documentation"))]

# Match fields only jurors (scoring:admin) may change, see update_match.
_PENALTY_FIELDS = frozenset({"is_disqualified", "yellow_card", "red_card"})


# The former unauthenticated /scoreboard/ws streamed the global channel of
# every event — including unpublished ones and their announcement texts — to
# anyone. No client used it any more; live screens use the per-event public
# stream (/api/v1/public/events/{slug}/ws), which honours the public_* flags.


async def _broadcast_ranking_update(db: AsyncSession, event_id: str) -> None:
    # Sent after the commit, so clients re-fetching the ranking see the new score.
    publish_after_commit(db, event_id, "ranking_updated")


def _broadcast_schedule_update(db: AsyncSession, event_id: str, scheduled_match_id: str | None):
    """A head-to-head score also records the scheduled match's result (and may
    advance a bracket), so schedule and bracket views refresh too."""
    if scheduled_match_id:
        publish_after_commit(db, event_id, "schedule_updated", {"matchId": scheduled_match_id})


async def _season_event(db: AsyncSession, season_id: str, event_id: str | None) -> Event:
    return await service.resolve_event(db, season_id, event_id)


# ── Ranking access ────────────────────────────────────────────────────────────
#
# Rankings are readable without login only where the organizers published a
# scoreboard (spec 08): the event is public (published/live/completed, in a
# non-draft season) and has public_scoreboard switched on. Everything else
# needs scoring:read, so rankings of draft events do not leak to anyone who
# knows an id.

_PUBLIC_EVENT_STATUSES = ("published", "live", "completed")


async def _scoreboard_is_public(db: AsyncSession, event: Event) -> bool:
    if not event.public_scoreboard or event.status not in _PUBLIC_EVENT_STATUSES:
        return False
    season_status = (
        await db.execute(select(Season.status).where(Season.id == event.season_id))
    ).scalar_one_or_none()
    return season_status is not None and season_status != DRAFT


async def _authorize_ranking(
    db: AsyncSession,
    credentials: HTTPAuthorizationCredentials | None,
    event: Event | None,
) -> None:
    if event is not None and await _scoreboard_is_public(db, event):
        return
    if credentials is None:
        raise UnauthorizedError()
    user = await get_current_user(credentials, db)
    if not await has_elevated_access(db, user, "scoring:read"):
        raise ForbiddenError("Missing permissions: scoring:read")
    # The router guard (hide_draft_events) only sees an event id in the path
    # or query; a season route ranks the season's default event without one.
    # Rankings are cached per event, so the check must come before any read.
    if (
        event is not None
        and await is_draft_event(db, event.id)
        and not await has_elevated_access(db, user, DRAFT_READERS)
    ):
        raise NotFoundError("Event not found")


async def _season_ranking_event(
    db: AsyncSession,
    credentials: HTTPAuthorizationCredentials | None,
    season_id: str,
    event_id: str | None,
) -> Event:
    """Authorize a season ranking read and return the event it ranks.

    The event is looked up read-only before the check, so an anonymous request
    never creates the season's fallback event or learns whether an id exists.
    """
    if event_id:
        found = await db.get(Event, event_id)
        event = found if found is not None and found.season_id == season_id else None
    else:
        event = await service.find_default_event(db, season_id)
    await _authorize_ranking(db, credentials, event)
    return await _season_event(db, season_id, event_id)


async def _event_for_ranking(
    db: AsyncSession, credentials: HTTPAuthorizationCredentials | None, event_id: str
) -> Event:
    await _authorize_ranking(db, credentials, await db.get(Event, event_id))
    return await event_svc.get_event(db, event_id)


# ── Matches ───────────────────────────────────────────────────────────────────


@router.get("/seasons/{season_id}/schema", response_model=ScoringSchemaResponse | None)
async def get_scoring_schema(
    season_id: str,
    competition_level_id: str | None = Query(None),
    event_id: str | None = Query(None),
    _=Depends(require_permission("scoring:read")),
    db: AsyncSession = Depends(get_db),
):
    """The active scoring schema (scored fields + multipliers) for a season.

    With `event_id`, an event-specific schema version wins over the season's.
    """
    return await service.get_active_schema(db, season_id, competition_level_id, event_id)


@router.get("/seasons/{season_id}/matches", response_model=list[MatchListItem])
async def list_matches(
    season_id: str,
    team_id: str | None = Query(None),
    phase_id: str | None = Query(None),
    is_practice: bool | None = Query(None),
    event_id: str | None = Query(None),
    limit: int | None = Query(None, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    current_user=Depends(require_permission("scoring:read")),
    db: AsyncSession = Depends(get_db),
):
    """Matches of a season in entry order; `limit`/`offset` page through them.

    Without `limit` every match is returned. The schema snapshot of each run
    is left out (see GET /scoring/matches/{id}); foreign practice runs and
    notes are hidden unless the caller has scoring:admin.
    """
    scope = await scope_svc.team_scope(db, current_user)
    matches = await service.list_matches(
        db,
        season_id,
        team_id=team_id,
        phase_id=phase_id,
        event_id=event_id,
        is_practice=is_practice,
        team_scope=scope,
        limit=limit,
        offset=offset,
    )
    return [scope_svc.match_list_item(match, scope) for match in matches]


@router.post("/seasons/{season_id}/matches", response_model=MatchResponse, status_code=201)
async def create_match(
    season_id: str,
    body: MatchCreate,
    current_user=Depends(require_permission("scoring:write")),
    db: AsyncSession = Depends(get_db),
):
    # Organizers (scoring:admin) may score any team; mentors only their own.
    await assert_team_access(db, current_user, body.team_id, "scoring:admin")
    data = body.model_dump()
    data["season_id"] = season_id
    match = await service.create_match(db, data, current_user.id)
    _broadcast_schedule_update(db, match.event_id, match.scheduled_match_id)
    await _broadcast_ranking_update(db, match.event_id)
    return match


@router.post(
    "/seasons/{season_id}/matches/bulk", response_model=list[MatchResponse], status_code=201
)
async def bulk_create_matches(
    season_id: str,
    body: ScoreBulkEntry,
    current_user=Depends(require_permission("scoring:write")),
    db: AsyncSession = Depends(get_db),
):
    # Same scoping as the single-match route — otherwise this endpoint would
    # be a way around it. Checked for all entries before anything is written,
    # with the caller's permissions and teams looked up once.
    if not await has_elevated_access(db, current_user, "scoring:admin"):
        own = await own_team_ids(db, current_user)
        if any(entry.team_id not in own for entry in body.entries):
            raise ForbiddenError("You may only access your own team")
    # The ranking tables are re-ranked once for the whole batch, not per entry.
    rank_refresh = service.RankRefresh()
    results = []
    for entry in body.entries:
        data = entry.model_dump()
        data["season_id"] = season_id
        match = await service.create_match(db, data, current_user.id, rank_refresh=rank_refresh)
        _broadcast_schedule_update(db, match.event_id, match.scheduled_match_id)
        results.append(match)
    await rank_refresh.run(db)
    for event_id in {m.event_id for m in results}:
        await _broadcast_ranking_update(db, event_id)
    return results


@router.get("/matches/{match_id}", response_model=MatchResponse)
async def get_match(
    match_id: str,
    current_user=Depends(require_permission("scoring:read")),
    db: AsyncSession = Depends(get_db),
):
    match = await service.get_match(db, match_id)
    scope = await scope_svc.team_scope(db, current_user)
    scope_svc.assert_match_visible(match, scope)
    return scope_svc.match_view(match, scope)


@router.patch("/matches/{match_id}", response_model=MatchResponse)
async def update_match(
    match_id: str,
    body: MatchUpdate,
    current_user=Depends(require_permission("scoring:write")),
    db: AsyncSession = Depends(get_db),
):
    # Organizers may edit any match; mentors only their own team's.
    existing = await service.get_match(db, match_id)
    await assert_team_access(db, current_user, existing.team_id, "scoring:admin")
    changes = body.model_dump(exclude_none=True)
    # Cards and disqualifications are referee decisions: a mentor editing the
    # own team's score must not be able to set or lift them.
    if _PENALTY_FIELDS & changes.keys() and not await has_elevated_access(
        db, current_user, "scoring:admin"
    ):
        raise ForbiddenError("Only jurors may set cards or disqualifications")
    version_before = existing.version
    match = await service.update_match(db, match_id, changed_by=current_user.id, **changes)
    _broadcast_schedule_update(db, match.event_id, match.scheduled_match_id)
    await _broadcast_ranking_update(db, match.event_id)
    if match.version != version_before:
        # The score actually changed: let the team know (push to its members).
        from modules.events.notifications import notify_score_corrected

        await notify_score_corrected(
            db, match.event_id, match.team_id, match.id, match.round_number
        )
    return match


@router.get("/matches/{match_id}/revisions", response_model=list[ScoreRevisionResponse])
async def list_score_revisions(
    match_id: str,
    current_user=Depends(require_permission("scoring:read")),
    db: AsyncSession = Depends(get_db),
):
    """A match's score history; still available after the match was deleted."""
    revisions = await service.list_revisions(db, match_id)
    scope = await scope_svc.team_scope(db, current_user)
    scope_svc.assert_revisions_visible(revisions, scope)
    return [scope_svc.revision_view(revision, scope) for revision in revisions]


@router.put("/matches/{match_id}/confirm", response_model=MatchResponse)
async def confirm_match(
    match_id: str,
    body: MatchConfirm | None = None,
    current_user=Depends(require_permission("scoring:admin")),
    db: AsyncSession = Depends(get_db),
):
    """Confirm a score; the season's required referee checklist items must be ticked."""
    return await service.confirm_match(
        db, match_id, current_user.id, body.checklist if body else None
    )


@router.delete("/matches/{match_id}", status_code=204)
async def delete_match(
    match_id: str,
    reason: str | None = Query(None, max_length=1000),
    current_user=Depends(require_permission("scoring:admin")),
    db: AsyncSession = Depends(get_db),
):
    match = await service.get_match(db, match_id)
    event_id = match.event_id
    scheduled_match_id = match.scheduled_match_id
    await service.delete_match(db, match_id, deleted_by=current_user.id, reason=reason)
    _broadcast_schedule_update(db, event_id, scheduled_match_id)
    await _broadcast_ranking_update(db, event_id)


@router.get("/events/{event_id}/revisions", response_model=list[ScoreRevisionResponse])
async def list_event_score_revisions(
    event_id: str,
    team_id: str | None = Query(None),
    current_user=Depends(require_permission("scoring:read")),
    db: AsyncSession = Depends(get_db),
):
    """Score audit trail of an event, newest first, including deleted matches."""
    await event_svc.get_event(db, event_id)
    scope = await scope_svc.team_scope(db, current_user)
    revisions = await service.list_event_revisions(db, event_id, team_id, team_scope=scope)
    return [scope_svc.revision_view(revision, scope) for revision in revisions]


@router.get("/events/{event_id}/result-revisions", response_model=list[ResultRevisionResponse])
async def list_result_revisions(
    event_id: str,
    kind: str | None = Query(None, pattern="^(de|aerial|doc|jbc)$"),
    team_id: str | None = Query(None),
    _=Depends(require_permission("scoring:read")),
    db: AsyncSession = Depends(get_db),
):
    """Audit trail of the DE, aerial and documentation results of an event."""
    event = await event_svc.get_event(db, event_id)
    return await comp_svc.list_result_revisions(db, event, kind, team_id)


# ── Ranking ───────────────────────────────────────────────────────────────────


@router.get("/seasons/{season_id}/ranking", response_model=list[RankingResponse])
async def get_ranking(
    season_id: str,
    competition_level_id: str | None = Query(None),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
):
    """Seeding ranking of the season's default event.

    Readable without login only when that event's scoreboard is public (see
    _authorize_ranking); otherwise scoring:read is required.
    """
    event = await _season_ranking_event(db, credentials, season_id, None)
    return await service.get_ranking(db, season_id, competition_level_id, event_id=event.id)


# ── Enhanced Ranking (with team names + category) ─────────────────────────────


async def _extended_ranking(
    db: AsyncSession, event: Event, category: str | None
) -> list[TeamRankingEntry]:
    rankings = await service.get_ranking(
        db, event_id=event.id, category=category, include_disqualified=True
    )
    names_result = await db.execute(
        select(Team.id, Team.name).where(Team.id.in_([r.team_id for r in rankings]))
    )
    names = {team_id: name for team_id, name in names_result.all()}
    return [
        TeamRankingEntry(
            rank=r.rank,
            disqualified=r.disqualified,
            team_id=r.team_id,
            team_name=names.get(r.team_id),
            category=r.category or service.DEFAULT_CATEGORY,
            seed_score=r.seed_score,
            best_score=r.best_score,
            average_score=r.average_score,
            rounds_played=r.rounds_played,
            tiebreaker=r.tiebreaker,
        )
        for r in rankings
    ]


async def _cached_extended_ranking(
    request: Request, db: AsyncSession, event: Event, category: str | None
):
    async def compute() -> bytes:
        return dump_json(list[TeamRankingEntry], await _extended_ranking(db, event, category))

    payload = await cached_payload("ranking-extended", event.id, category or "*", compute)
    return conditional_response(request, payload, public=False)


@router.get("/seasons/{season_id}/ranking/extended", response_model=list[TeamRankingEntry])
async def get_ranking_extended(
    request: Request,
    season_id: str,
    category: str | None = Query(None),
    event_id: str | None = Query(None),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
):
    """Seeding ranking enriched with team name and category.

    Ranks are per category (Botball and Open are separate competitions); a
    red-carded team is listed with `disqualified` and no rank. Cached per
    event and answered with an ETag (304 on If-None-Match).
    """
    event = await _season_ranking_event(db, credentials, season_id, event_id)
    return await _cached_extended_ranking(request, db, event, category)


@router.get("/events/{event_id}/ranking/extended", response_model=list[TeamRankingEntry])
async def get_event_ranking_extended(
    request: Request,
    event_id: str,
    category: str | None = Query(None),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
):
    """Seeding ranking of one event, with team names and per-category ranks."""
    event = await _event_for_ranking(db, credentials, event_id)
    return await _cached_extended_ranking(request, db, event, category)


# ── Overall Ranking ───────────────────────────────────────────────────────────


async def _cached_overall_ranking(
    request: Request, db: AsyncSession, event: Event, category: str | None
):
    season = await season_svc.get_season(db, event.season_id)
    categories = [category] if category else list(season.active_categories or ["botball"])

    async def compute() -> bytes:
        entries = await formula_svc.compute_overall_ranking(db, event.id, categories)
        return dump_json(list[OverallRankingEntry], entries)

    payload = await cached_payload("ranking-overall", event.id, ",".join(categories), compute)
    return conditional_response(request, payload, public=False)


@router.get("/events/{event_id}/ranking/overall", response_model=list[OverallRankingEntry])
async def get_event_overall_ranking(
    request: Request,
    event_id: str,
    category: str | None = Query(None),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
):
    """Overall ranking for one event, using its season's formula set."""
    event = await _event_for_ranking(db, credentials, event_id)
    return await _cached_overall_ranking(request, db, event, category)


# ── Double Elimination ────────────────────────────────────────────────────────


@router.get(
    "/events/{event_id}/de-results", response_model=list[DEResultResponse], dependencies=_DE
)
async def list_event_de_results(
    event_id: str,
    _=Depends(require_permission("scoring:read")),
    db: AsyncSession = Depends(get_db),
):
    return await comp_svc.get_de_results(db, await event_svc.get_event(db, event_id))


@router.put(
    "/events/{event_id}/de-results", response_model=list[DEResultResponse], dependencies=_DE
)
async def bulk_upsert_event_de_results(
    event_id: str,
    body: list[DEResultUpsert],
    current_user=Depends(require_permission("scoring:admin")),
    db: AsyncSession = Depends(get_db),
):
    event = await event_svc.get_event(db, event_id)
    rows = await comp_svc.bulk_upsert_de_results(
        db, event, [e.model_dump() for e in body], current_user.id
    )
    await _broadcast_ranking_update(db, event.id)
    return rows


@router.put(
    "/events/{event_id}/de-results/{team_id}", response_model=DEResultResponse, dependencies=_DE
)
async def upsert_event_de_result(
    event_id: str,
    team_id: str,
    body: DEResultUpsert,
    current_user=Depends(require_permission("scoring:admin")),
    db: AsyncSession = Depends(get_db),
):
    event = await event_svc.get_event(db, event_id)
    data = body.model_dump()
    data["team_id"] = team_id
    row = await comp_svc.upsert_de_result(db, event, data, current_user.id)
    await _broadcast_ranking_update(db, event.id)
    return row


# ── Aerial ────────────────────────────────────────────────────────────────────


@router.get(
    "/events/{event_id}/aerial-results",
    response_model=list[AerialResultResponse],
    dependencies=_AERIAL,
)
async def list_event_aerial_results(
    event_id: str,
    _=Depends(require_permission("scoring:read")),
    db: AsyncSession = Depends(get_db),
):
    return await comp_svc.get_aerial_results(db, await event_svc.get_event(db, event_id))


@router.get("/events/{event_id}/aerial-ranking", dependencies=_AERIAL)
async def get_event_aerial_ranking(
    event_id: str,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
):
    return await comp_svc.get_aerial_ranking(
        db, await _event_for_ranking(db, credentials, event_id)
    )


@router.put(
    "/events/{event_id}/aerial-results",
    response_model=list[AerialResultResponse],
    dependencies=_AERIAL,
)
async def bulk_upsert_event_aerial_results(
    event_id: str,
    body: list[AerialResultUpsert],
    current_user=Depends(require_permission("scoring:admin")),
    db: AsyncSession = Depends(get_db),
):
    event = await event_svc.get_event(db, event_id)
    rows = await comp_svc.bulk_upsert_aerial_results(
        db, event, [e.model_dump() for e in body], current_user.id
    )
    await _broadcast_ranking_update(db, event.id)
    return rows


@router.put(
    "/events/{event_id}/aerial-results/{team_id}",
    response_model=AerialResultResponse,
    dependencies=_AERIAL,
)
async def upsert_event_aerial_result(
    event_id: str,
    team_id: str,
    body: AerialResultUpsert,
    current_user=Depends(require_permission("scoring:admin")),
    db: AsyncSession = Depends(get_db),
):
    event = await event_svc.get_event(db, event_id)
    data = body.model_dump()
    data["team_id"] = team_id
    row = await comp_svc.upsert_aerial_result(db, event, data, current_user.id)
    await _broadcast_ranking_update(db, event.id)
    return row


# ── Junior Botball Challenge ──────────────────────────────────────────────────


@router.get("/events/{event_id}/jbc-results", response_model=list[JBCResultResponse])
async def list_event_jbc_results(
    event_id: str,
    _=Depends(require_permission("scoring:read")),
    db: AsyncSession = Depends(get_db),
):
    """Points for solved challenges per team (Junior Botball Challenge)."""
    return await comp_svc.get_jbc_results(db, await event_svc.get_event(db, event_id))


@router.get("/events/{event_id}/jbc-ranking")
async def get_event_jbc_ranking(
    event_id: str,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
):
    return await comp_svc.get_jbc_ranking(db, await _event_for_ranking(db, credentials, event_id))


@router.put("/events/{event_id}/jbc-results", response_model=list[JBCResultResponse])
async def bulk_upsert_event_jbc_results(
    event_id: str,
    body: list[JBCResultUpsert],
    current_user=Depends(require_permission("scoring:admin")),
    db: AsyncSession = Depends(get_db),
):
    event = await event_svc.get_event(db, event_id)
    rows = await comp_svc.bulk_upsert_jbc_results(
        db, event, [e.model_dump() for e in body], current_user.id
    )
    await _broadcast_ranking_update(db, event.id)
    return rows


@router.put("/events/{event_id}/jbc-results/{team_id}", response_model=JBCResultResponse)
async def upsert_event_jbc_result(
    event_id: str,
    team_id: str,
    body: JBCResultUpsert,
    current_user=Depends(require_permission("scoring:admin")),
    db: AsyncSession = Depends(get_db),
):
    event = await event_svc.get_event(db, event_id)
    data = body.model_dump()
    data["team_id"] = team_id
    row = await comp_svc.upsert_jbc_result(db, event, data, current_user.id)
    await _broadcast_ranking_update(db, event.id)
    return row


# ── Documentation Scoring ─────────────────────────────────────────────────────


@router.get(
    "/events/{event_id}/doc-scores", response_model=list[DocScoreResponse], dependencies=_DOC
)
async def list_event_doc_scores(
    event_id: str,
    _=Depends(require_permission("scoring:read")),
    db: AsyncSession = Depends(get_db),
):
    return await comp_svc.get_doc_scores(db, await event_svc.get_event(db, event_id))


@router.put(
    "/events/{event_id}/doc-scores", response_model=list[DocScoreResponse], dependencies=_DOC
)
async def bulk_upsert_event_doc_scores(
    event_id: str,
    body: list[DocScoreUpsert],
    current_user=Depends(require_permission("scoring:admin")),
    db: AsyncSession = Depends(get_db),
):
    event = await event_svc.get_event(db, event_id)
    rows = await comp_svc.bulk_upsert_doc_scores(
        db, event, [e.model_dump() for e in body], current_user.id
    )
    await _broadcast_ranking_update(db, event.id)
    return rows


@router.put(
    "/events/{event_id}/doc-scores/{team_id}", response_model=DocScoreResponse, dependencies=_DOC
)
async def upsert_event_doc_score(
    event_id: str,
    team_id: str,
    body: DocScoreUpsert,
    current_user=Depends(require_permission("scoring:admin")),
    db: AsyncSession = Depends(get_db),
):
    event = await event_svc.get_event(db, event_id)
    data = body.model_dump()
    data["team_id"] = team_id
    row = await comp_svc.upsert_doc_score(db, event, data, current_user.id)
    await _broadcast_ranking_update(db, event.id)
    return row
