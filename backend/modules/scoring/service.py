"""Event-aware scoring, immutable revisions, and ranking computation."""

from collections import Counter, defaultdict
from collections.abc import Iterable
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Select, delete, func, literal, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from core.exceptions import ConflictError, NotFoundError, ValidationError
from modules.events.models import Event, EventPhase, EventRegistration, ScheduledMatch
from modules.scoring import rules_service, sheet, tiebreak
from modules.scoring.models import Match, Ranking, ScoreRevision, ScoringSchema
from modules.seasons.lifecycle import ensure_writable
from modules.seasons.models import SeasonPhase
from modules.teams.models import TeamSeasonRegistration

#: Phase kinds as far as scoring is concerned. Everything that is neither
#: seeding nor double seeding (DE, alliance, finals, …) never feeds the seed
#: score.
SEEDING = "seeding"
DOUBLE_SEEDING = "double_seeding"

DEFAULT_CATEGORY = "botball"


def compute_seed_score(scores: list[float]) -> float:
    """Average of the best two seeding rounds.

    `scores` are the official round scores as returned by official_run_score,
    i.e. a disqualified round is already a 0 and still counts as a round played.
    """
    if not scores:
        return 0.0
    top = sorted(scores, reverse=True)[:2]
    return sum(top) / len(top)


def official_run_score(
    total_score: float | None, is_disqualified: bool, round_lost: bool = False
) -> float:
    """The value a seeding round contributes, per the game review.

    "Seed scores of less than 0 will be counted as 0", and a disqualified round
    is a round with 0 points — it is not dropped, so it can be one of the
    "best two" a team with a single good run is averaged over. A lost round
    ("never left the start box", motors still running) is treated the same
    way: 0 points, but a round played. ``total_score`` already contains the
    end-contact bonus of a head-to-head round (see rules_service), so seeding,
    double seeding and the formula inputs all see the same value.
    """
    if is_disqualified or round_lost:
        return 0.0
    return max(0.0, float(total_score or 0.0))


def select_matches_with_kind(*columns: Any) -> Select:
    """SELECT `columns` from matches, plus the phase kind each match belongs to.

    The kind is resolved from the match's event phase, else from its scheduled
    match's phase, else from the legacy season phase. A match linked to none of
    them was entered free-hand (score entry page, bulk entry) and counts as a
    seeding round — that is the only kind the free-hand entry offers.
    """
    direct_phase = aliased(EventPhase)
    scheduled_phase = aliased(EventPhase)
    kind = func.coalesce(
        direct_phase.phase_type,
        scheduled_phase.phase_type,
        SeasonPhase.phase_type,
        literal(SEEDING),
    ).label("phase_kind")
    return (
        select(*columns, kind)
        .select_from(Match)
        .outerjoin(direct_phase, direct_phase.id == Match.event_phase_id)
        .outerjoin(ScheduledMatch, ScheduledMatch.id == Match.scheduled_match_id)
        .outerjoin(scheduled_phase, scheduled_phase.id == ScheduledMatch.phase_id)
        .outerjoin(SeasonPhase, SeasonPhase.id == Match.phase_id)
    )


async def team_categories(
    db: AsyncSession, event: Event, team_ids: Iterable[str] | None = None
) -> dict[str, str]:
    """Category per team at this event.

    The event registration wins (a team can start in Open at one event and in
    Botball at another); the season registration is the fallback for events
    whose field was never registered explicitly.
    """
    wanted = set(team_ids) if team_ids is not None else None
    categories: dict[str, str] = {}
    season_rows = await db.execute(
        select(TeamSeasonRegistration.team_id, TeamSeasonRegistration.category).where(
            TeamSeasonRegistration.season_id == event.season_id
        )
    )
    for team_id, category in season_rows.all():
        if category and (wanted is None or team_id in wanted):
            categories[team_id] = category
    event_rows = await db.execute(
        select(EventRegistration.team_id, EventRegistration.category).where(
            EventRegistration.event_id == event.id
        )
    )
    for team_id, category in event_rows.all():
        if category and (wanted is None or team_id in wanted):
            categories[team_id] = category
    return categories


async def red_carded_teams(db: AsyncSession, event_id: str) -> set[str]:
    """Teams with a red card in any official match at this event.

    A red card disqualifies the team from the whole tournament ranking, not
    just from the round it was shown in.
    """
    result = await db.execute(
        select(Match.team_id)
        .where(
            Match.event_id == event_id,
            Match.red_card.is_(True),
            Match.is_practice.is_(False),
        )
        .distinct()
    )
    return set(result.scalars().all())


def competition_ranks(values: list[tuple[str, float]]) -> dict[str, int]:
    """1224 ranking: equal values share a rank and the next rank skips."""
    ordered = sorted(values, key=lambda item: (-item[1], item[0]))
    ranks: dict[str, int] = {}
    previous: float | None = None
    rank = 0
    for position, (key, value) in enumerate(ordered, start=1):
        if previous is None or value < previous:
            rank = position
            previous = value
        ranks[key] = rank
    return ranks


def compute_match_total(
    raw_scores: dict, schema_fields: list[dict], definition: dict | None = None
) -> float:
    """Score-sheet total of one run (see modules.scoring.sheet).

    This is the single source of truth for a run's sheet score: match entry,
    corrections, OCR acceptance and the analytics recomputation all use it.

    When a schema is defined it is authoritative: keys it doesn't define score
    nothing, and a field's ``max_value`` is enforced. Both matter because the
    client supplies raw_scores — previously an invented key scored with an
    implicit multiplier of 1, and any value was accepted, so a mentor could
    score themselves arbitrarily high on their own match.

    Flat schemas add up Σ value × multiplier; a structured ``definition`` adds
    area multipliers, either-or groups and sides A/B. With no schema configured
    the legacy fallback still applies: values are summed as-is.
    """
    return sheet.compute_total(raw_scores, schema_fields, definition)


def validate_raw_scores(
    raw_scores: dict, schema_fields: list[dict], definition: dict | None = None
) -> None:
    """Apply the validation bounds embedded in a versioned scoring schema."""
    sheet.validate(raw_scores, schema_fields, definition)


async def find_default_event(db: AsyncSession, season_id: str) -> Event | None:
    """The season's default (earliest) event, without creating one."""
    result = await db.execute(
        select(Event)
        .where(Event.season_id == season_id)
        .order_by(Event.starts_at.asc().nullsfirst(), Event.created_at)
    )
    return result.scalars().first()


async def get_default_event(db: AsyncSession, season_id: str) -> Event:
    event = await find_default_event(db, season_id)
    if event:
        return event

    # Keeps seasons created through imports and old test helpers valid. Normal API
    # season creation already creates this event in the same transaction.
    from modules.events.module_access import modules_for_season
    from modules.seasons.models import Season

    event = Event(
        season_id=season_id,
        name="Main Event",
        slug=f"event-{season_id}",
        status="draft",
        active_modules=modules_for_season(await db.get(Season, season_id)),
    )
    db.add(event)
    await db.flush()
    return event


async def resolve_event(db: AsyncSession, season_id: str, event_id: str | None = None) -> Event:
    event = await db.get(Event, event_id) if event_id else await get_default_event(db, season_id)
    if not event:
        raise NotFoundError("Event not found")
    if event.season_id != season_id:
        raise ValidationError("Event does not belong to the selected season")
    return event


async def get_active_schema(
    db: AsyncSession,
    season_id: str,
    competition_level_id: str | None = None,
    event_id: str | None = None,
) -> ScoringSchema | None:
    query = select(ScoringSchema).where(
        ScoringSchema.season_id == season_id,
        ScoringSchema.is_active.is_(True),
    )
    if competition_level_id:
        query = query.where(ScoringSchema.competition_level_id == competition_level_id)
    else:
        query = query.where(ScoringSchema.competition_level_id.is_(None))
    if event_id:
        event_result = await db.execute(
            query.where(ScoringSchema.event_id == event_id).order_by(ScoringSchema.version.desc())
        )
        event_schema = event_result.scalars().first()
        if event_schema:
            return event_schema
    result = await db.execute(
        query.where(ScoringSchema.event_id.is_(None)).order_by(ScoringSchema.version.desc())
    )
    return result.scalars().first()


async def create_schema_version(
    db: AsyncSession,
    event: Event,
    competition_level_id: str | None,
    fields: list[dict],
    activate: bool = True,
    definition: dict | None = None,
) -> ScoringSchema:
    await ensure_writable(db, event_id=event.id)
    if definition is not None:
        # The structured sheet is authoritative; `fields` lists its inputs so
        # flat consumers (entry forms, OCR mapping, exports) keep working.
        fields = sheet.flat_fields(definition)
    scope = [
        ScoringSchema.season_id == event.season_id,
        ScoringSchema.event_id == event.id,
        ScoringSchema.competition_level_id == competition_level_id
        if competition_level_id
        else ScoringSchema.competition_level_id.is_(None),
    ]
    result = await db.execute(
        select(func.coalesce(func.max(ScoringSchema.version), 0)).where(*scope)
    )
    version = int(result.scalar_one()) + 1
    if activate:
        await db.execute(update(ScoringSchema).where(*scope).values(is_active=False))
    schema = ScoringSchema(
        season_id=event.season_id,
        event_id=event.id,
        competition_level_id=competition_level_id,
        fields=fields,
        definition=definition,
        version=version,
        is_active=activate,
    )
    db.add(schema)
    await db.flush()
    return schema


async def list_matches(
    db: AsyncSession,
    season_id: str | None = None,
    team_id: str | None = None,
    phase_id: str | None = None,
    event_id: str | None = None,
    is_practice: bool | None = None,
) -> list[Match]:
    query = select(Match).order_by(Match.round_number, Match.created_at)
    if season_id:
        query = query.where(Match.season_id == season_id)
    if event_id:
        query = query.where(Match.event_id == event_id)
    if team_id:
        query = query.where(Match.team_id == team_id)
    if phase_id:
        query = query.where(Match.event_phase_id == phase_id)
    if is_practice is not None:
        query = query.where(Match.is_practice.is_(is_practice))
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_match(db: AsyncSession, match_id: str) -> Match:
    match = await db.get(Match, match_id)
    if not match:
        raise NotFoundError("Match not found")
    return match


def _score_state(match: Match) -> dict:
    return {
        "raw_scores": deepcopy(match.raw_scores),
        "total_score": match.total_score,
        "sheet_score": match.sheet_score,
        "bonus_score": match.bonus_score,
        "is_disqualified": match.is_disqualified,
        "round_lost": match.round_lost,
        "round_lost_reason": match.round_lost_reason,
        "end_contact": match.end_contact,
        "tiebreak_values": deepcopy(match.tiebreak_values or {}),
        "yellow_card": match.yellow_card,
        "red_card": match.red_card,
        "notes": match.notes,
    }


def _revision(
    match: Match,
    changed_by: str | None,
    previous: dict | None,
    reason: str | None = None,
) -> ScoreRevision:
    current = _score_state(match)
    return ScoreRevision(
        match_id=match.id,
        match_ref=match.id,
        team_id=match.team_id,
        event_id=match.event_id,
        revision=match.version,
        previous_raw_scores=previous and previous["raw_scores"],
        new_raw_scores=current["raw_scores"],
        previous_total_score=previous and previous["total_score"],
        new_total_score=current["total_score"],
        previous_value=previous,
        new_value=current,
        reason=reason,
        changed_by=changed_by,
    )


async def create_match(db: AsyncSession, data: dict, entered_by: str) -> Match:
    match_data = data.copy()
    provided_total = match_data.pop("total_score", None)
    season_id = match_data.pop("season_id")
    await ensure_writable(db, season_id=season_id)
    event = await resolve_event(db, season_id, match_data.pop("event_id", None))
    await ensure_writable(db, event_id=event.id)
    idempotency_key = match_data.get("idempotency_key")
    if idempotency_key:
        result = await db.execute(select(Match).where(Match.idempotency_key == idempotency_key))
        existing = result.scalar_one_or_none()
        if existing:
            if existing.event_id != event.id:
                raise ConflictError("Idempotency key is already used by another event")
            return existing

    scheduled_match_id = match_data.get("scheduled_match_id")
    if scheduled_match_id:
        scheduled_match = await db.get(ScheduledMatch, scheduled_match_id)
        if not scheduled_match or scheduled_match.event_id != event.id:
            raise ValidationError("Scheduled match does not belong to this event")
        match_data.setdefault("event_phase_id", scheduled_match.phase_id)
        match_data.setdefault("round_number", scheduled_match.round_number)
        match_data.setdefault("table_number", scheduled_match.table_number)

    schema = await get_active_schema(
        db,
        season_id,
        match_data.get("competition_level_id"),
        event.id,
    )
    schema_fields = schema.fields if schema else []
    definition = schema.definition if schema else None
    raw_scores = match_data.get("raw_scores", {})
    validate_raw_scores(raw_scores, schema_fields, definition)
    _validate_round_lost(match_data)
    sheet_total = (
        compute_match_total(raw_scores, schema_fields, definition)
        if raw_scores or schema
        else float(provided_total or 0.0)
    )
    snapshot = None
    if schema:
        snapshot = {
            "id": schema.id,
            "version": schema.version,
            "fields": deepcopy(schema.fields),
            "definition": deepcopy(schema.definition),
        }
    match_data["tiebreak_values"] = match_data.get("tiebreak_values") or {}

    match = Match(
        **match_data,
        season_id=event.season_id,
        event_id=event.id,
        schema_snapshot=snapshot,
        sheet_score=sheet_total,
        bonus_score=0.0,
        entered_by=entered_by,
    )
    rules_service.apply_round_rules(match)
    db.add(match)
    await db.flush()
    opponents = await _apply_head_to_head(db, match)
    db.add(_revision(match, entered_by, None))
    await _recompute_ranking(
        db,
        event.id,
        match.team_id,
        match.competition_level_id,
        match.event_phase_id,
    )
    await _recompute_opponents(db, opponents)
    return match


def _validate_round_lost(data: dict) -> None:
    reason = data.get("round_lost_reason")
    if reason is not None and reason not in tiebreak.LOSE_ROUND_REASONS:
        raise ValidationError(
            f"round_lost_reason must be one of {', '.join(tiebreak.LOSE_ROUND_REASONS)}"
        )
    if data.get("round_lost") is False:
        data["round_lost_reason"] = None


async def _apply_head_to_head(db: AsyncSession, match: Match) -> list[Match]:
    """Re-apply contact bonus and outcome of the head-to-head match `match` belongs to.

    Returns the opponent rows, whose total may have changed with it.
    """
    if not match.scheduled_match_id or match.is_practice:
        return []
    await rules_service.apply_head_to_head(db, match.scheduled_match_id, match.season_id)
    others = await rules_service.head_to_head_matches(db, match.scheduled_match_id)
    return [m for m in others if m.id != match.id]


async def _recompute_opponents(db: AsyncSession, opponents: list[Match]) -> None:
    for other in opponents:
        await _recompute_ranking(
            db, other.event_id, other.team_id, other.competition_level_id, other.event_phase_id
        )


async def update_match(
    db: AsyncSession,
    match_id: str,
    *,
    changed_by: str | None = None,
    expected_version: int | None = None,
    correction_reason: str | None = None,
    **kwargs,
) -> Match:
    match = await get_match(db, match_id)
    await ensure_writable(db, event_id=match.event_id)
    if expected_version is not None and expected_version != match.version:
        raise ConflictError(f"Score was changed by another user (current version: {match.version})")
    previous = _score_state(match)
    kwargs.pop("total_score", None)  # always derived, never set directly
    if "raw_scores" in kwargs:
        snapshot = match.schema_snapshot or {}
        schema_fields = snapshot.get("fields", [])
        definition = snapshot.get("definition")
        validate_raw_scores(kwargs["raw_scores"], schema_fields, definition)
        kwargs["sheet_score"] = compute_match_total(kwargs["raw_scores"], schema_fields, definition)
    _validate_round_lost(kwargs)
    for key, value in kwargs.items():
        setattr(match, key, value)
    rules_service.apply_round_rules(match)
    await db.flush()
    opponents = await _apply_head_to_head(db, match)
    if _score_state(match) == previous:
        return match
    match.version += 1
    await db.flush()
    db.add(_revision(match, changed_by, previous, correction_reason))
    await _recompute_ranking(
        db,
        match.event_id,
        match.team_id,
        match.competition_level_id,
        match.event_phase_id,
    )
    await _recompute_opponents(db, opponents)
    if previous["red_card"] != match.red_card:
        await refresh_all_levels(db, match.event_id)
    return match


async def list_revisions(db: AsyncSession, match_id: str) -> list[ScoreRevision]:
    """History of one match — also after the match itself was deleted."""
    result = await db.execute(
        select(ScoreRevision)
        .where(ScoreRevision.match_ref == match_id)
        .order_by(ScoreRevision.revision)
    )
    revisions = list(result.scalars().all())
    if not revisions:
        await get_match(db, match_id)  # 404 for an id that never existed
    return revisions


async def list_event_revisions(
    db: AsyncSession, event_id: str, team_id: str | None = None, limit: int = 500
) -> list[ScoreRevision]:
    """Score audit trail of a whole event, newest first, including deletions."""
    query = select(ScoreRevision).where(ScoreRevision.event_id == event_id)
    if team_id:
        query = query.where(ScoreRevision.team_id == team_id)
    result = await db.execute(query.order_by(ScoreRevision.created_at.desc()).limit(limit))
    return list(result.scalars().all())


async def confirm_match(
    db: AsyncSession, match_id: str, confirmed_by: str, checklist: dict | None = None
) -> Match:
    """Confirm an official score after the season's referee checklist.

    Every required checklist item must be ticked — in this request or on a
    checklist saved with the match earlier. The ticked items are stored with
    the match as the record of what the juror checked.
    """
    match = await get_match(db, match_id)
    await ensure_writable(db, event_id=match.event_id)
    rules = await rules_service.get_rules(db, match.season_id)
    items = {item["key"]: item for item in rules.referee_checklist}
    state = dict(match.checklist or {})
    for key, value in (checklist or {}).items():
        if key not in items:
            raise ValidationError(f"'{key}' is not an item of the referee checklist")
        state[key] = bool(value)
    missing = [
        str(item.get("label") or key)
        for key, item in items.items()
        if item.get("required", True) and not state.get(key)
    ]
    if missing:
        raise ValidationError("Referee checklist incomplete: " + ", ".join(missing))
    if items:
        match.checklist = state
    match.confirmed_by = confirmed_by
    match.confirmed_at = datetime.now(UTC)
    return match


async def delete_match(
    db: AsyncSession,
    match_id: str,
    *,
    deleted_by: str | None = None,
    reason: str | None = None,
) -> None:
    """Delete a match but keep its score history.

    A final revision records the deletion (who, when, the last state), and the
    existing revisions are detached from the row instead of being cascaded
    away with it — an official score must stay traceable after a correction.
    """
    match = await get_match(db, match_id)
    await ensure_writable(db, event_id=match.event_id)
    event_id = match.event_id
    team_id = match.team_id
    level_id = match.competition_level_id
    phase_id = match.event_phase_id
    scheduled_match_id = match.scheduled_match_id if not match.is_practice else None
    season_id = match.season_id

    previous = _score_state(match)
    await db.execute(
        update(ScoreRevision).where(ScoreRevision.match_id == match.id).values(match_id=None)
    )
    db.add(
        ScoreRevision(
            match_id=None,
            match_ref=match.id,
            team_id=match.team_id,
            event_id=match.event_id,
            revision=match.version + 1,
            previous_raw_scores=previous["raw_scores"],
            new_raw_scores=previous["raw_scores"],
            previous_total_score=previous["total_score"],
            new_total_score=previous["total_score"],
            previous_value=previous,
            new_value={**previous, "deleted": True},
            reason=reason or "Match deleted",
            changed_by=deleted_by,
        )
    )
    await db.flush()
    await db.delete(match)
    await db.flush()
    await _recompute_ranking(db, event_id, team_id, level_id, phase_id)
    if scheduled_match_id:
        # The opponent loses any contact bonus this row gave it.
        await rules_service.apply_head_to_head(db, scheduled_match_id, season_id)
        await _recompute_opponents(
            db, await rules_service.head_to_head_matches(db, scheduled_match_id)
        )
    if previous["red_card"]:
        await refresh_all_levels(db, event_id)


async def refresh_all_levels(db: AsyncSession, event_id: str) -> None:
    """Re-rank every competition level of an event.

    A red card counts for the whole event, so granting or lifting one changes
    the team's rows at every level, not only at the level of that match.
    """
    result = await db.execute(
        select(Ranking.competition_level_id).where(Ranking.event_id == event_id).distinct()
    )
    for level_id in result.scalars().all():
        await _refresh_ranks(db, event_id, level_id)


async def _recompute_ranking(
    db: AsyncSession,
    event_id: str,
    team_id: str,
    competition_level_id: str | None,
    event_phase_id: str | None = None,
) -> None:
    """Rebuild one team's seeding ranking row at an event.

    The seeding ranking is event-wide (event_phase_id NULL): it combines every
    seeding round of the team, however the rounds were entered, and ignores DE,
    double-seeding, alliance and final matches. `event_phase_id` is accepted
    for backwards compatibility; which phase the triggering match belonged to
    does not change what the ranking contains.
    """
    del event_phase_id
    event = await db.get(Event, event_id)
    if not event:
        # Backwards compatibility for callers of the former season-scoped
        # service API. New code always passes an event id.
        event = await get_default_event(db, event_id)
        event_id = event.id

    level_filter = (
        Match.competition_level_id == competition_level_id
        if competition_level_id
        else Match.competition_level_id.is_(None)
    )
    # Only the scoring columns are needed. Selecting whole Match rows here
    # pulled raw_scores and schema_snapshot JSON for every match on every write.
    rows = (
        await db.execute(
            select_matches_with_kind(
                Match.total_score, Match.is_disqualified, Match.round_lost
            ).where(
                Match.event_id == event_id,
                Match.team_id == team_id,
                Match.is_practice.is_(False),  # practice runs never count
                level_filter,
            )
        )
    ).all()
    scores = [
        official_run_score(total, disqualified, round_lost)
        for total, disqualified, round_lost, kind in rows
        if kind == SEEDING
    ]

    level_ranking_filter = (
        Ranking.competition_level_id == competition_level_id
        if competition_level_id
        else Ranking.competition_level_id.is_(None)
    )
    # Rows keyed by a phase are from before the seeding ranking was made
    # event-wide; they would list the team twice.
    await db.execute(
        delete(Ranking).where(
            Ranking.event_id == event_id,
            Ranking.team_id == team_id,
            Ranking.event_phase_id.is_not(None),
            level_ranking_filter,
        )
    )
    ranking_filter = [
        Ranking.event_id == event_id,
        Ranking.team_id == team_id,
        Ranking.event_phase_id.is_(None),
        level_ranking_filter,
    ]
    if not scores:
        await db.execute(delete(Ranking).where(*ranking_filter))
        await _refresh_ranks(db, event_id, competition_level_id)
        return

    result = await db.execute(select(Ranking).where(*ranking_filter))
    ranking = result.scalar_one_or_none()
    if not ranking:
        ranking = Ranking(
            season_id=event.season_id,
            event_id=event_id,
            event_phase_id=None,
            team_id=team_id,
            competition_level_id=competition_level_id,
            rank=None,
        )
        db.add(ranking)
    ranking.seed_score = compute_seed_score(scores)
    ranking.best_score = max(scores)
    ranking.average_score = sum(scores) / len(scores)
    ranking.rounds_played = len(scores)
    await db.flush()
    await _refresh_ranks(db, event_id, competition_level_id)


async def _refresh_ranks(
    db: AsyncSession,
    event_id: str,
    competition_level_id: str | None,
    event_phase_id: str | None = None,
) -> None:
    """Re-rank an event's seeding table.

    Ranks are computed per registration category — Botball and Open teams are
    separate competitions — and red-carded teams take no rank at all. Equal
    seed scores are separated by the season's tie-breakers (applied to the
    runs that make up the seed score); teams no criterion separates — or all
    tied teams when the season configures none — share a rank (1, 2, 2, 4).
    The red-card flag is refreshed for every row, since the card may have
    been shown in a match of another phase or level.
    """
    del event_phase_id
    event = await db.get(Event, event_id)
    if not event:
        # Backwards compatibility for callers of the former season-scoped API.
        event = await get_default_event(db, event_id)
        event_id = event.id
    query = select(Ranking).where(Ranking.event_id == event_id, Ranking.event_phase_id.is_(None))
    query = (
        query.where(Ranking.competition_level_id == competition_level_id)
        if competition_level_id
        else query.where(Ranking.competition_level_id.is_(None))
    )
    rankings = list((await db.execute(query)).scalars().all())
    if not rankings:
        return
    categories = await team_categories(db, event, [r.team_id for r in rankings])
    red_carded = await red_carded_teams(db, event_id)

    by_category: dict[str, list[Ranking]] = defaultdict(list)
    for ranking in rankings:
        ranking.category = categories.get(ranking.team_id, DEFAULT_CATEGORY)
        ranking.disqualified = ranking.team_id in red_carded
        by_category[ranking.category].append(ranking)

    criteria = (await rules_service.get_rules(db, event.season_id)).tiebreakers
    for rows in by_category.values():
        ranked = [r for r in rows if not r.disqualified]
        ranks = competition_ranks([(r.team_id, r.seed_score) for r in ranked])
        decided_by: dict[str, str | None] = {}
        rank_counts = Counter(ranks.values())
        tied = {team_id for team_id, rank in ranks.items() if rank_counts[rank] > 1}
        if criteria and tied:
            values = await _seed_tiebreak_values(db, event_id, tied, criteria, competition_level_id)
            items = [
                tiebreak.RankedItem(
                    id=r.team_id, score=r.seed_score, values=values.get(r.team_id, {})
                )
                for r in sorted(ranked, key=lambda r: r.team_id)
            ]
            for item in tiebreak.rank_with_tiebreakers(items, criteria):
                ranks[item.id] = item.rank
                decided_by[item.id] = item.decided_by
        for ranking in rows:
            ranking.rank = ranks.get(ranking.team_id)
            ranking.tiebreaker = decided_by.get(ranking.team_id)
    await db.flush()


async def _seed_tiebreak_values(
    db: AsyncSession,
    event_id: str,
    team_ids: set[str],
    criteria: list[dict],
    competition_level_id: str | None,
) -> dict[str, dict[str, float | None]]:
    """Tie-breaker values per team, summed over the runs its seed score counts.

    These are the same runs _recompute_ranking averages: the best two official
    seeding rounds. A disqualified or lost round is one of them when it has to
    be (a team with a single scored run), but its sheet contributes nothing.
    """
    level_filter = (
        Match.competition_level_id == competition_level_id
        if competition_level_id
        else Match.competition_level_id.is_(None)
    )
    rows = (
        await db.execute(
            select_matches_with_kind(Match).where(
                Match.event_id == event_id,
                Match.team_id.in_(team_ids),
                Match.is_practice.is_(False),
                level_filter,
            )
        )
    ).all()
    runs: dict[str, list[Match]] = defaultdict(list)
    for match, kind in rows:
        if kind == SEEDING:
            runs[match.team_id].append(match)
    out: dict[str, dict[str, float | None]] = {}
    for team_id, matches in runs.items():
        counted = sorted(
            matches,
            key=lambda m: official_run_score(m.total_score, m.is_disqualified, m.round_lost),
            reverse=True,
        )[:2]
        out[team_id] = tiebreak.sum_values(
            [
                tiebreak.match_values(
                    criteria,
                    m.raw_scores,
                    m.tiebreak_values,
                    rules_service.snapshot_definition(m),
                )
                if not (m.is_disqualified or m.round_lost)
                else {}
                for m in counted
            ]
        )
    return out


async def get_ranking(
    db: AsyncSession,
    season_id: str | None = None,
    competition_level_id: str | None = None,
    event_id: str | None = None,
    event_phase_id: str | None = None,
    *,
    category: str | None = None,
    include_disqualified: bool = False,
) -> list[Ranking]:
    """The event's seeding ranking.

    Red-carded teams are left out unless `include_disqualified` is set: they
    have no rank, and consumers that print a ranking (exports, the public
    scoreboard) must not list them as if they had placed.
    """
    if not event_id:
        if not season_id:
            raise ValidationError("season_id or event_id is required")
        event_id = (await get_default_event(db, season_id)).id
    if event_phase_id:
        # The seeding ranking is event-wide; asking for it by one of the
        # event's seeding phases still returns it, any other phase has none.
        phase = await db.get(EventPhase, event_phase_id)
        if not phase or phase.event_id != event_id or phase.phase_type != SEEDING:
            return []
    query = select(Ranking).where(Ranking.event_id == event_id, Ranking.event_phase_id.is_(None))
    if competition_level_id:
        query = query.where(Ranking.competition_level_id == competition_level_id)
    if category:
        query = query.where(func.coalesce(Ranking.category, DEFAULT_CATEGORY) == category)
    if not include_disqualified:
        query = query.where(Ranking.disqualified.is_(False))
    result = await db.execute(
        query.order_by(Ranking.rank.asc().nulls_last(), Ranking.category, Ranking.seed_score.desc())
    )
    return list(result.scalars().all())
