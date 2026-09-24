from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import (
    assert_team_access,
    require_permission,
)
from core.database import get_db
from core.live import publish_after_commit
from modules.events import service as event_svc
from modules.events.models import Event
from modules.events.module_access import require_season_event_module
from modules.scoring import competition_service as comp_svc
from modules.scoring import formula_service as formula_svc
from modules.scoring import service
from modules.scoring.competition_schemas import (
    AerialResultResponse,
    AerialResultUpsert,
    DEResultResponse,
    DEResultUpsert,
    DocScoreResponse,
    DocScoreUpsert,
    OverallRankingEntry,
    ResultRevisionResponse,
    TeamRankingEntry,
)
from modules.scoring.schemas import (
    MatchCreate,
    MatchResponse,
    MatchUpdate,
    RankingResponse,
    ScoreBulkEntry,
    ScoreRevisionResponse,
    ScoringSchemaResponse,
)
from modules.seasons import service as season_svc
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


# The former unauthenticated /scoreboard/ws streamed the global channel of
# every event — including unpublished ones and their announcement texts — to
# anyone. No client used it any more; live screens use the per-event public
# stream (/api/v1/public/events/{slug}/ws), which honours the public_* flags.


async def _broadcast_ranking_update(db: AsyncSession, event_id: str) -> None:
    # Sent after the commit, so clients re-fetching the ranking see the new score.
    publish_after_commit(db, event_id, "ranking_updated")


async def _season_event(db: AsyncSession, season_id: str, event_id: str | None) -> Event:
    return await service.resolve_event(db, season_id, event_id)


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


@router.get("/seasons/{season_id}/matches", response_model=list[MatchResponse])
async def list_matches(
    season_id: str,
    team_id: str | None = Query(None),
    phase_id: str | None = Query(None),
    is_practice: bool | None = Query(None),
    event_id: str | None = Query(None),
    _=Depends(require_permission("scoring:read")),
    db: AsyncSession = Depends(get_db),
):
    return await service.list_matches(
        db,
        season_id,
        team_id=team_id,
        phase_id=phase_id,
        event_id=event_id,
        is_practice=is_practice,
    )


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
    results = []
    for entry in body.entries:
        # Same scoping as the single-match route — otherwise this endpoint
        # would be a way around it.
        await assert_team_access(db, current_user, entry.team_id, "scoring:admin")
        data = entry.model_dump()
        data["season_id"] = season_id
        results.append(await service.create_match(db, data, current_user.id))
    for event_id in {m.event_id for m in results}:
        await _broadcast_ranking_update(db, event_id)
    return results


@router.get("/matches/{match_id}", response_model=MatchResponse)
async def get_match(
    match_id: str,
    _=Depends(require_permission("scoring:read")),
    db: AsyncSession = Depends(get_db),
):
    return await service.get_match(db, match_id)


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
    version_before = existing.version
    match = await service.update_match(
        db,
        match_id,
        changed_by=current_user.id,
        **body.model_dump(exclude_none=True),
    )
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
    _=Depends(require_permission("scoring:read")),
    db: AsyncSession = Depends(get_db),
):
    """A match's score history; still available after the match was deleted."""
    return await service.list_revisions(db, match_id)


@router.put("/matches/{match_id}/confirm", response_model=MatchResponse)
async def confirm_match(
    match_id: str,
    current_user=Depends(require_permission("scoring:admin")),
    db: AsyncSession = Depends(get_db),
):
    return await service.confirm_match(db, match_id, current_user.id)


@router.delete("/matches/{match_id}", status_code=204)
async def delete_match(
    match_id: str,
    reason: str | None = Query(None, max_length=1000),
    current_user=Depends(require_permission("scoring:admin")),
    db: AsyncSession = Depends(get_db),
):
    match = await service.get_match(db, match_id)
    event_id = match.event_id
    await service.delete_match(db, match_id, deleted_by=current_user.id, reason=reason)
    await _broadcast_ranking_update(db, event_id)


@router.get("/events/{event_id}/revisions", response_model=list[ScoreRevisionResponse])
async def list_event_score_revisions(
    event_id: str,
    team_id: str | None = Query(None),
    _=Depends(require_permission("scoring:read")),
    db: AsyncSession = Depends(get_db),
):
    """Score audit trail of an event, newest first, including deleted matches."""
    await event_svc.get_event(db, event_id)
    return await service.list_event_revisions(db, event_id, team_id)


@router.get("/events/{event_id}/result-revisions", response_model=list[ResultRevisionResponse])
async def list_result_revisions(
    event_id: str,
    kind: str | None = Query(None, pattern="^(de|aerial|doc)$"),
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
    db: AsyncSession = Depends(get_db),
):
    """Public endpoint – no auth required for scoreboard display.

    NOTE: unlike GET /v1/public/events/{slug}/ranking this does not honour the
    event's public_scoreboard / public_results flags.
    """
    return await service.get_ranking(db, season_id, competition_level_id)


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
    names = dict(names_result.tuples().all())
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
        )
        for r in rankings
    ]


@router.get("/seasons/{season_id}/ranking/extended", response_model=list[TeamRankingEntry])
async def get_ranking_extended(
    season_id: str,
    category: str | None = Query(None),
    event_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Seeding ranking enriched with team name and category.

    Ranks are per category (Botball and Open are separate competitions); a
    red-carded team is listed with `disqualified` and no rank.
    """
    event = await _season_event(db, season_id, event_id)
    return await _extended_ranking(db, event, category)


@router.get("/events/{event_id}/ranking/extended", response_model=list[TeamRankingEntry])
async def get_event_ranking_extended(
    event_id: str,
    category: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Seeding ranking of one event, with team names and per-category ranks."""
    event = await event_svc.get_event(db, event_id)
    return await _extended_ranking(db, event, category)


# ── Overall Ranking ───────────────────────────────────────────────────────────


@router.get("/seasons/{season_id}/ranking/overall", response_model=list[OverallRankingEntry])
async def get_overall_ranking(
    season_id: str,
    category: str | None = Query(None),
    event_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Overall ranking computed from the season's configured formula set.

    Results are recorded per event, so this ranks one event: the one named by
    `event_id`, otherwise the season's default event — the same one the other
    season routes read and write, so a result entered through them shows here.
    """
    season = await season_svc.get_season(db, season_id)
    event = await _season_event(db, season_id, event_id)
    categories = [category] if category else list(season.active_categories or ["botball"])
    return await formula_svc.compute_overall_ranking(db, event.id, categories)


@router.get("/events/{event_id}/ranking/overall", response_model=list[OverallRankingEntry])
async def get_event_overall_ranking(
    event_id: str,
    category: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Overall ranking for one event, using its season's formula set."""
    event = await event_svc.get_event(db, event_id)
    season = await season_svc.get_season(db, event.season_id)
    categories = [category] if category else list(season.active_categories or ["botball"])
    return await formula_svc.compute_overall_ranking(db, event_id, categories)


# ── Double Elimination ────────────────────────────────────────────────────────


@router.get(
    "/seasons/{season_id}/de-results", response_model=list[DEResultResponse], dependencies=_DE
)
async def list_de_results(
    season_id: str,
    event_id: str | None = Query(None),
    _=Depends(require_permission("scoring:read")),
    db: AsyncSession = Depends(get_db),
):
    return await comp_svc.get_de_results(db, await _season_event(db, season_id, event_id))


@router.put(
    "/seasons/{season_id}/de-results", response_model=list[DEResultResponse], dependencies=_DE
)
async def bulk_upsert_de_results(
    season_id: str,
    body: list[DEResultUpsert],
    event_id: str | None = Query(None),
    current_user=Depends(require_permission("scoring:admin")),
    db: AsyncSession = Depends(get_db),
):
    event = await _season_event(db, season_id, event_id)
    entries = [e.model_dump() for e in body]
    rows = await comp_svc.bulk_upsert_de_results(db, event, entries, current_user.id)
    await _broadcast_ranking_update(db, event.id)
    return rows


@router.put(
    "/seasons/{season_id}/de-results/{team_id}", response_model=DEResultResponse, dependencies=_DE
)
async def upsert_de_result(
    season_id: str,
    team_id: str,
    body: DEResultUpsert,
    event_id: str | None = Query(None),
    current_user=Depends(require_permission("scoring:admin")),
    db: AsyncSession = Depends(get_db),
):
    event = await _season_event(db, season_id, event_id)
    data = body.model_dump()
    data["team_id"] = team_id
    row = await comp_svc.upsert_de_result(db, event, data, current_user.id)
    await _broadcast_ranking_update(db, event.id)
    return row


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
    "/seasons/{season_id}/aerial-results",
    response_model=list[AerialResultResponse],
    dependencies=_AERIAL,
)
async def list_aerial_results(
    season_id: str,
    event_id: str | None = Query(None),
    _=Depends(require_permission("scoring:read")),
    db: AsyncSession = Depends(get_db),
):
    return await comp_svc.get_aerial_results(db, await _season_event(db, season_id, event_id))


@router.get("/seasons/{season_id}/aerial-ranking", dependencies=_AERIAL)
async def get_aerial_ranking(
    season_id: str,
    event_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    return await comp_svc.get_aerial_ranking(db, await _season_event(db, season_id, event_id))


@router.put(
    "/seasons/{season_id}/aerial-results",
    response_model=list[AerialResultResponse],
    dependencies=_AERIAL,
)
async def bulk_upsert_aerial_results(
    season_id: str,
    body: list[AerialResultUpsert],
    event_id: str | None = Query(None),
    current_user=Depends(require_permission("scoring:admin")),
    db: AsyncSession = Depends(get_db),
):
    event = await _season_event(db, season_id, event_id)
    entries = [e.model_dump() for e in body]
    rows = await comp_svc.bulk_upsert_aerial_results(db, event, entries, current_user.id)
    await _broadcast_ranking_update(db, event.id)
    return rows


@router.put(
    "/seasons/{season_id}/aerial-results/{team_id}",
    response_model=AerialResultResponse,
    dependencies=_AERIAL,
)
async def upsert_aerial_result(
    season_id: str,
    team_id: str,
    body: AerialResultUpsert,
    event_id: str | None = Query(None),
    current_user=Depends(require_permission("scoring:admin")),
    db: AsyncSession = Depends(get_db),
):
    event = await _season_event(db, season_id, event_id)
    data = body.model_dump()
    data["team_id"] = team_id
    row = await comp_svc.upsert_aerial_result(db, event, data, current_user.id)
    await _broadcast_ranking_update(db, event.id)
    return row


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
    db: AsyncSession = Depends(get_db),
):
    return await comp_svc.get_aerial_ranking(db, await event_svc.get_event(db, event_id))


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


# ── Documentation Scoring ─────────────────────────────────────────────────────


@router.get(
    "/seasons/{season_id}/doc-scores", response_model=list[DocScoreResponse], dependencies=_DOC
)
async def list_doc_scores(
    season_id: str,
    event_id: str | None = Query(None),
    _=Depends(require_permission("scoring:read")),
    db: AsyncSession = Depends(get_db),
):
    return await comp_svc.get_doc_scores(db, await _season_event(db, season_id, event_id))


@router.put(
    "/seasons/{season_id}/doc-scores", response_model=list[DocScoreResponse], dependencies=_DOC
)
async def bulk_upsert_doc_scores(
    season_id: str,
    body: list[DocScoreUpsert],
    event_id: str | None = Query(None),
    current_user=Depends(require_permission("scoring:admin")),
    db: AsyncSession = Depends(get_db),
):
    event = await _season_event(db, season_id, event_id)
    entries = [e.model_dump() for e in body]
    rows = await comp_svc.bulk_upsert_doc_scores(db, event, entries, current_user.id)
    await _broadcast_ranking_update(db, event.id)
    return rows


@router.put(
    "/seasons/{season_id}/doc-scores/{team_id}", response_model=DocScoreResponse, dependencies=_DOC
)
async def upsert_doc_score(
    season_id: str,
    team_id: str,
    body: DocScoreUpsert,
    event_id: str | None = Query(None),
    current_user=Depends(require_permission("scoring:admin")),
    db: AsyncSession = Depends(get_db),
):
    event = await _season_event(db, season_id, event_id)
    data = body.model_dump()
    data["team_id"] = team_id
    row = await comp_svc.upsert_doc_score(db, event, data, current_user.id)
    await _broadcast_ranking_update(db, event.id)
    return row


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
