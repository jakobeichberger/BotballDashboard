"""Routes for season rules, schema templates, tie-breakers, parts challenges,
scouting and GCER qualification."""

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import require_permission
from core.database import get_db
from core.live import publish_after_commit
from modules.scoring import extras_service as svc
from modules.scoring import sheet_templates
from modules.scoring.extras_schemas import (
    DEPlacementEntry,
    ExternalTeamCreate,
    ExternalTeamResponse,
    ExternalTeamUpdate,
    HeadToHeadOutcome,
    ObservationCreate,
    ObservationResponse,
    OpponentRankingEntry,
    PartsChallengeCreate,
    PartsChallengeResponse,
    PartsChallengeRuling,
    QualificationResponse,
    QualificationStatusEntry,
    QualifyRequest,
    RegisteredTeam,
    RegisterQualifiedRequest,
    RuleSetResponse,
    RuleSetUpdate,
    SchemaClone,
    SchemaListEntry,
    SchemaTemplateResponse,
    ScoutingNoteCreate,
    ScoutingNoteResponse,
    ScoutingNoteUpdate,
    TiebreakerPreset,
)
from modules.scoring.routes import _broadcast_ranking_update
from modules.scoring.schemas import ScoringSchemaResponse
from modules.scoring.scouting_pdf import build_scouting_pdf

router = APIRouter(prefix="/scoring", tags=["scoring-extras"])


# ── Season rules ──────────────────────────────────────────────────────────────


@router.get("/seasons/{season_id}/rules", response_model=RuleSetResponse)
async def get_rules(
    season_id: str,
    _=Depends(require_permission("scoring:read")),
    db: AsyncSession = Depends(get_db),
):
    """Tie-breaker order, finals replay rule, contact bonus and referee checklist."""
    return await svc.get_rule_set(db, season_id)


@router.put("/seasons/{season_id}/rules", response_model=RuleSetResponse)
async def put_rules(
    season_id: str,
    body: RuleSetUpdate,
    _=Depends(require_permission("scoring:admin")),
    db: AsyncSession = Depends(get_db),
):
    rules = await svc.put_rule_set(db, season_id, body.model_dump(mode="json"))
    # New tie-breakers can reorder shared seed scores in every event of the season.
    for event_id in await svc.season_event_ids(db, season_id):
        await _broadcast_ranking_update(db, event_id)
    return rules


@router.get("/tiebreaker-presets", response_model=list[TiebreakerPreset])
async def list_tiebreaker_presets(_=Depends(require_permission("scoring:read"))):
    """Tie-breaker lists transcribed from the 2024/2025/2026 game reviews."""
    return svc.tiebreaker_presets()


# ── Schema templates and cloning ──────────────────────────────────────────────


@router.get("/schema-templates", response_model=list[SchemaTemplateResponse])
async def list_schema_templates(_=Depends(require_permission("scoring:read"))):
    """Score sheets 2024/2025 (complete) and 2026 (structure) as starting points."""
    return sheet_templates.list_templates()


@router.get("/schemas", response_model=list[SchemaListEntry])
async def list_schemas(
    season_id: str | None = Query(None),
    _=Depends(require_permission("scoring:read")),
    db: AsyncSession = Depends(get_db),
):
    """Active schema versions of every event/level — sources for "clone from"."""
    return await svc.list_schemas(db, season_id)


@router.post(
    "/events/{event_id}/scoring-schema/clone",
    response_model=ScoringSchemaResponse,
    status_code=201,
)
async def clone_schema(
    event_id: str,
    body: SchemaClone,
    _=Depends(require_permission("scoring:admin")),
    db: AsyncSession = Depends(get_db),
):
    """Copy another event's/level's schema (e.g. ECER → GCER) as a new version."""
    return await svc.clone_schema(
        db, event_id, body.source_schema_id, body.competition_level_id, body.activate
    )


# ── Head to head, DE placement ────────────────────────────────────────────────


@router.get("/scheduled-matches/{scheduled_match_id}/outcome", response_model=HeadToHeadOutcome)
async def get_head_to_head_outcome(
    scheduled_match_id: str,
    _=Depends(require_permission("scoring:read")),
    db: AsyncSession = Depends(get_db),
):
    """Winner of a head-to-head match and what decided it (score, tie-breaker, …)."""
    return await svc.head_to_head_outcome(db, scheduled_match_id)


@router.get("/events/{event_id}/de-placement", response_model=list[DEPlacementEntry])
async def get_de_placement(
    event_id: str,
    _=Depends(require_permission("scoring:read")),
    db: AsyncSession = Depends(get_db),
):
    return await svc.de_placement(db, event_id)


# ── Parts challenges ──────────────────────────────────────────────────────────


@router.get("/events/{event_id}/parts-challenges", response_model=list[PartsChallengeResponse])
async def list_parts_challenges(
    event_id: str,
    _=Depends(require_permission("scoring:read")),
    db: AsyncSession = Depends(get_db),
):
    return await svc.list_parts_challenges(db, event_id)


@router.post(
    "/events/{event_id}/parts-challenges",
    response_model=PartsChallengeResponse,
    status_code=201,
)
async def create_parts_challenge(
    event_id: str,
    body: PartsChallengeCreate,
    current_user=Depends(require_permission("scoring:admin")),
    db: AsyncSession = Depends(get_db),
):
    return await svc.create_parts_challenge(db, event_id, body.model_dump(), current_user.id)


@router.put("/parts-challenges/{challenge_id}/ruling", response_model=PartsChallengeResponse)
async def rule_parts_challenge(
    challenge_id: str,
    body: PartsChallengeRuling,
    current_user=Depends(require_permission("scoring:admin")),
    db: AsyncSession = Depends(get_db),
):
    challenge = await svc.rule_parts_challenge(
        db, challenge_id, body.upheld, body.ruling_note, current_user.id
    )
    # The DQ can flip a head-to-head result and with it the bracket.
    if challenge.scheduled_match_id:
        publish_after_commit(
            db, challenge.event_id, "schedule_updated", {"matchId": challenge.scheduled_match_id}
        )
    await _broadcast_ranking_update(db, challenge.event_id)
    return challenge


# ── Scouting ──────────────────────────────────────────────────────────────────


@router.get("/seasons/{season_id}/external-teams", response_model=list[ExternalTeamResponse])
async def list_external_teams(
    season_id: str,
    _=Depends(require_permission("scoring:read")),
    db: AsyncSession = Depends(get_db),
):
    return await svc.list_external_teams(db, season_id)


@router.post("/external-teams", response_model=ExternalTeamResponse, status_code=201)
async def create_external_team(
    body: ExternalTeamCreate,
    current_user=Depends(require_permission("scoring:write")),
    db: AsyncSession = Depends(get_db),
):
    return await svc.create_external_team(db, body.model_dump(), current_user)


@router.patch("/external-teams/{external_team_id}", response_model=ExternalTeamResponse)
async def update_external_team(
    external_team_id: str,
    body: ExternalTeamUpdate,
    current_user=Depends(require_permission("scoring:write")),
    db: AsyncSession = Depends(get_db),
):
    return await svc.update_external_team(
        db, external_team_id, body.model_dump(exclude_unset=True), current_user
    )


@router.delete("/external-teams/{external_team_id}", status_code=204)
async def delete_external_team(
    external_team_id: str,
    _=Depends(require_permission("scoring:admin")),
    db: AsyncSession = Depends(get_db),
):
    await svc.delete_external_team(db, external_team_id)


@router.get("/events/{event_id}/scouting/notes", response_model=list[ScoutingNoteResponse])
async def list_scouting_notes(
    event_id: str,
    external_team_id: str | None = Query(None),
    current_user=Depends(require_permission("scoring:read")),
    db: AsyncSession = Depends(get_db),
):
    """Organizers see all notes, everybody else only their own teams' notes."""
    return await svc.list_notes(db, event_id, current_user, external_team_id)


@router.post(
    "/events/{event_id}/scouting/notes", response_model=ScoutingNoteResponse, status_code=201
)
async def create_scouting_note(
    event_id: str,
    body: ScoutingNoteCreate,
    current_user=Depends(require_permission("scoring:write")),
    db: AsyncSession = Depends(get_db),
):
    return await svc.create_note(db, event_id, body.model_dump(), current_user)


@router.patch("/scouting/notes/{note_id}", response_model=ScoutingNoteResponse)
async def update_scouting_note(
    note_id: str,
    body: ScoutingNoteUpdate,
    current_user=Depends(require_permission("scoring:write")),
    db: AsyncSession = Depends(get_db),
):
    return await svc.update_note(db, note_id, body.model_dump(exclude_unset=True), current_user)


@router.delete("/scouting/notes/{note_id}", status_code=204)
async def delete_scouting_note(
    note_id: str,
    current_user=Depends(require_permission("scoring:write")),
    db: AsyncSession = Depends(get_db),
):
    await svc.delete_note(db, note_id, current_user)


@router.get("/events/{event_id}/scouting/observations", response_model=list[ObservationResponse])
async def list_observations(
    event_id: str,
    external_team_id: str | None = Query(None),
    current_user=Depends(require_permission("scoring:read")),
    db: AsyncSession = Depends(get_db),
):
    return await svc.list_observations(db, event_id, current_user, external_team_id)


@router.post(
    "/events/{event_id}/scouting/observations",
    response_model=ObservationResponse,
    status_code=201,
)
async def create_observation(
    event_id: str,
    body: ObservationCreate,
    current_user=Depends(require_permission("scoring:write")),
    db: AsyncSession = Depends(get_db),
):
    return await svc.create_observation(db, event_id, body.model_dump(), current_user)


@router.delete("/scouting/observations/{observation_id}", status_code=204)
async def delete_observation(
    observation_id: str,
    current_user=Depends(require_permission("scoring:write")),
    db: AsyncSession = Depends(get_db),
):
    await svc.delete_observation(db, observation_id, current_user)


@router.get("/events/{event_id}/opponent-ranking", response_model=list[OpponentRankingEntry])
async def get_opponent_ranking(
    event_id: str,
    current_user=Depends(require_permission("scoring:read")),
    db: AsyncSession = Depends(get_db),
):
    """Own teams (official seeding) and external teams (observed scores) ranked together."""
    return await svc.opponent_ranking(db, event_id, current_user)


@router.get("/events/{event_id}/scouting/report.pdf")
async def export_scouting_report(
    event_id: str,
    current_user=Depends(require_permission("scoring:read")),
    db: AsyncSession = Depends(get_db),
):
    report = await svc.scouting_report(db, event_id, current_user)
    pdf = build_scouting_pdf(report)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="scouting-{event_id}.pdf"'},
    )


# ── Qualification (ECER → GCER) ───────────────────────────────────────────────


@router.get("/seasons/{season_id}/qualifications", response_model=list[QualificationResponse])
async def list_qualifications(
    season_id: str,
    level_id: str | None = Query(None),
    _=Depends(require_permission("scoring:read")),
    db: AsyncSession = Depends(get_db),
):
    return await svc.list_qualifications(db, season_id, level_id)


@router.get(
    "/seasons/{season_id}/qualification-status", response_model=list[QualificationStatusEntry]
)
async def get_qualification_status(
    season_id: str,
    level_id: str = Query(...),
    _=Depends(require_permission("scoring:read")),
    db: AsyncSession = Depends(get_db),
):
    """Candidates for a level and whether each is already qualified."""
    return await svc.qualification_status(db, season_id, level_id)


@router.post(
    "/levels/{level_id}/qualify", response_model=list[QualificationResponse], status_code=201
)
async def qualify_teams(
    level_id: str,
    body: QualifyRequest,
    current_user=Depends(require_permission("seasons:write")),
    db: AsyncSession = Depends(get_db),
):
    """Admin: mark teams as qualified for this level (manual, with a note)."""
    return await svc.qualify_teams(
        db,
        level_id,
        body.season_id,
        body.team_ids,
        body.note,
        body.source_event_id,
        current_user.id,
    )


@router.delete("/qualifications/{qualification_id}", status_code=204)
async def revoke_qualification(
    qualification_id: str,
    _=Depends(require_permission("seasons:write")),
    db: AsyncSession = Depends(get_db),
):
    await svc.revoke_qualification(db, qualification_id)


@router.post(
    "/events/{event_id}/register-qualified",
    response_model=list[RegisteredTeam],
    status_code=201,
)
async def register_qualified_teams(
    event_id: str,
    body: RegisterQualifiedRequest,
    _=Depends(require_permission("events:write")),
    db: AsyncSession = Depends(get_db),
):
    """Register every team qualified for the level at this (e.g. GCER) event."""
    return await svc.register_qualified(db, event_id, body.level_id, body.category)
