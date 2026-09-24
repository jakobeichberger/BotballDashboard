"""Event-aware scoring, immutable revisions, and ranking computation."""

from copy import deepcopy
from datetime import UTC, datetime

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.exceptions import ConflictError, NotFoundError, ValidationError
from modules.events.models import Event, ScheduledMatch
from modules.scoring import rules_service, sheet, tiebreak
from modules.scoring.models import Match, Ranking, ScoreRevision, ScoringSchema


def compute_seed_score(scores: list[float]) -> float:
    """Average of the best two official, non-disqualified scores."""
    if not scores:
        return 0.0
    top = sorted(scores, reverse=True)[:2]
    return sum(top) / len(top)


def compute_match_total(
    raw_scores: dict, schema_fields: list[dict], definition: dict | None = None
) -> float:
    """Score-sheet total of one run (see modules.scoring.sheet).

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


async def get_default_event(db: AsyncSession, season_id: str) -> Event:
    result = await db.execute(
        select(Event)
        .where(Event.season_id == season_id)
        .order_by(Event.starts_at.asc().nullsfirst(), Event.created_at)
    )
    event = result.scalars().first()
    if event:
        return event

    # Keeps seasons created through imports and old test helpers valid. Normal API
    # season creation already creates this event in the same transaction.
    event = Event(
        season_id=season_id,
        name="Main Event",
        slug=f"event-{season_id}",
        status="draft",
        active_modules=["seeding"],
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
    event = await resolve_event(db, season_id, match_data.pop("event_id", None))
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
    total = (
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
        sheet_score=total,
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
    return match


async def list_revisions(db: AsyncSession, match_id: str) -> list[ScoreRevision]:
    await get_match(db, match_id)
    result = await db.execute(
        select(ScoreRevision)
        .where(ScoreRevision.match_id == match_id)
        .order_by(ScoreRevision.revision)
    )
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


async def delete_match(db: AsyncSession, match_id: str) -> None:
    match = await get_match(db, match_id)
    event_id = match.event_id
    team_id = match.team_id
    level_id = match.competition_level_id
    phase_id = match.event_phase_id
    scheduled_match_id = match.scheduled_match_id if not match.is_practice else None
    season_id = match.season_id
    await db.delete(match)
    await db.flush()
    await _recompute_ranking(db, event_id, team_id, level_id, phase_id)
    if scheduled_match_id:
        # The opponent loses any contact bonus this row gave it.
        await rules_service.apply_head_to_head(db, scheduled_match_id, season_id)
        await _recompute_opponents(
            db, await rules_service.head_to_head_matches(db, scheduled_match_id)
        )


async def _recompute_ranking(
    db: AsyncSession,
    event_id: str,
    team_id: str,
    competition_level_id: str | None,
    event_phase_id: str | None = None,
) -> None:
    event = await db.get(Event, event_id)
    if not event:
        # Backwards compatibility for callers of the former season-scoped
        # service API. New code always passes an event id.
        event = await get_default_event(db, event_id)
        event_id = event.id
    # Only the score is needed. Selecting whole Match rows here pulled the
    # raw_scores and schema_snapshot JSON (a full copy of the scoring schema)
    # for every match, on every score write.
    match_query = select(Match.total_score).where(
        Match.event_id == event_id,
        Match.team_id == team_id,
        Match.is_disqualified.is_(False),
        Match.is_practice.is_(False),  # practice runs never count toward the ranking
    )
    match_query = (
        match_query.where(Match.event_phase_id == event_phase_id)
        if event_phase_id
        else match_query.where(Match.event_phase_id.is_(None))
    )
    if competition_level_id:
        match_query = match_query.where(Match.competition_level_id == competition_level_id)
    else:
        match_query = match_query.where(Match.competition_level_id.is_(None))
    scores = list((await db.execute(match_query)).scalars().all())

    ranking_filter = [
        Ranking.event_id == event_id,
        Ranking.team_id == team_id,
        Ranking.event_phase_id == event_phase_id
        if event_phase_id
        else Ranking.event_phase_id.is_(None),
        Ranking.competition_level_id == competition_level_id
        if competition_level_id
        else Ranking.competition_level_id.is_(None),
    ]
    if not scores:
        await db.execute(delete(Ranking).where(*ranking_filter))
        await _refresh_ranks(db, event_id, competition_level_id, event_phase_id)
        return

    result = await db.execute(select(Ranking).where(*ranking_filter))
    ranking = result.scalar_one_or_none()
    if not ranking:
        ranking = Ranking(
            season_id=event.season_id,
            event_id=event_id,
            event_phase_id=event_phase_id,
            team_id=team_id,
            competition_level_id=competition_level_id,
            rank=0,
        )
        db.add(ranking)
    ranking.seed_score = compute_seed_score(scores)
    ranking.best_score = max(scores)
    ranking.average_score = sum(scores) / len(scores)
    ranking.rounds_played = len(scores)
    await db.flush()
    await _refresh_ranks(db, event_id, competition_level_id, event_phase_id)


async def _refresh_ranks(
    db: AsyncSession,
    event_id: str,
    competition_level_id: str | None,
    event_phase_id: str | None = None,
) -> None:
    event = await db.get(Event, event_id)
    if not event:
        # Backwards compatibility for callers of the former season-scoped API.
        event = await get_default_event(db, event_id)
        event_id = event.id
    query = select(Ranking).where(Ranking.event_id == event_id)
    query = (
        query.where(Ranking.event_phase_id == event_phase_id)
        if event_phase_id
        else query.where(Ranking.event_phase_id.is_(None))
    )
    query = (
        query.where(Ranking.competition_level_id == competition_level_id)
        if competition_level_id
        else query.where(Ranking.competition_level_id.is_(None))
    )
    result = await db.execute(query.order_by(Ranking.seed_score.desc(), Ranking.team_id))
    rankings = list(result.scalars().all())

    # Equal seed scores are ordered by the season's tie-breakers, applied to the
    # runs that make up the seed score (the best two). Teams nothing separates
    # keep the former order (team id) so ranks stay unique.
    by_team = {r.team_id: r for r in rankings}
    items = [
        tiebreak.RankedItem(id=r.team_id, score=r.seed_score, fallback=float(position))
        for position, r in enumerate(rankings)
    ]
    criteria = (await rules_service.get_rules(db, event.season_id)).tiebreakers
    counts: dict[float, int] = {}
    for r in rankings:
        counts[r.seed_score] = counts.get(r.seed_score, 0) + 1
    tied = {r.team_id for r in rankings if counts[r.seed_score] > 1}
    if criteria and tied:
        values = await _seed_tiebreak_values(
            db, event_id, tied, criteria, competition_level_id, event_phase_id
        )
        for item in items:
            item.values = values.get(item.id, {})
    for item in tiebreak.rank_with_tiebreakers(items, criteria):
        ranking = by_team[item.id]
        ranking.rank = item.rank
        ranking.tiebreaker = item.decided_by
    await db.flush()


async def _seed_tiebreak_values(
    db: AsyncSession,
    event_id: str,
    team_ids: set[str],
    criteria: list[dict],
    competition_level_id: str | None,
    event_phase_id: str | None,
) -> dict[str, dict[str, float | None]]:
    query = select(Match).where(
        Match.event_id == event_id,
        Match.team_id.in_(team_ids),
        Match.is_disqualified.is_(False),
        Match.is_practice.is_(False),
    )
    query = (
        query.where(Match.event_phase_id == event_phase_id)
        if event_phase_id
        else query.where(Match.event_phase_id.is_(None))
    )
    query = (
        query.where(Match.competition_level_id == competition_level_id)
        if competition_level_id
        else query.where(Match.competition_level_id.is_(None))
    )
    runs: dict[str, list[Match]] = {}
    for match in (await db.execute(query)).scalars():
        runs.setdefault(match.team_id, []).append(match)
    out: dict[str, dict[str, float | None]] = {}
    for team_id, matches in runs.items():
        counted = sorted(matches, key=lambda m: m.total_score, reverse=True)[:2]
        out[team_id] = tiebreak.sum_values(
            [
                tiebreak.match_values(
                    criteria,
                    m.raw_scores,
                    m.tiebreak_values,
                    rules_service.snapshot_definition(m),
                )
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
) -> list[Ranking]:
    if not event_id:
        if not season_id:
            raise ValidationError("season_id or event_id is required")
        event_id = (await get_default_event(db, season_id)).id
    query = select(Ranking).where(Ranking.event_id == event_id)
    if competition_level_id:
        query = query.where(Ranking.competition_level_id == competition_level_id)
    if event_phase_id:
        query = query.where(Ranking.event_phase_id == event_phase_id)
    result = await db.execute(query.order_by(Ranking.rank))
    return list(result.scalars().all())
