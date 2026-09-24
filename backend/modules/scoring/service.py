"""Event-aware scoring, immutable revisions, and ranking computation."""

from copy import deepcopy
from datetime import UTC, datetime

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.exceptions import ConflictError, NotFoundError, ValidationError
from modules.events.models import Event, ScheduledMatch
from modules.scoring.models import Match, Ranking, ScoreRevision, ScoringSchema


def compute_seed_score(scores: list[float]) -> float:
    """Average of the best two official, non-disqualified scores."""
    if not scores:
        return 0.0
    top = sorted(scores, reverse=True)[:2]
    return sum(top) / len(top)


def compute_match_total(raw_scores: dict, schema_fields: list[dict]) -> float:
    """Multiply each submitted field by the configured multiplier and sum it."""
    total = 0.0
    field_map = {field["key"]: field for field in schema_fields}
    for key, value in raw_scores.items():
        multiplier = field_map.get(key, {}).get("multiplier", 1)
        total += float(value) * float(multiplier)
    return round(total, 2)


def validate_raw_scores(raw_scores: dict, schema_fields: list[dict]) -> None:
    """Apply the validation bounds embedded in a versioned scoring schema."""
    field_map = {field["key"]: field for field in schema_fields}
    errors: list[str] = []
    for key, field in field_map.items():
        if field.get("required") and key not in raw_scores:
            errors.append(f"{key} is required")
    for key, value in raw_scores.items():
        submitted_field = field_map.get(key)
        if submitted_field is None and schema_fields:
            errors.append(f"{key} is not part of the active scoring schema")
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            errors.append(f"{key} must be numeric")
            continue
        if submitted_field:
            minimum = submitted_field.get("min_value", submitted_field.get("min"))
            maximum = submitted_field.get("max_value", submitted_field.get("max"))
            if minimum is not None and number < float(minimum):
                errors.append(f"{key} must be at least {minimum}")
            if maximum is not None and number > float(maximum):
                errors.append(f"{key} must be at most {maximum}")
    if errors:
        raise ValidationError("; ".join(errors))


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
) -> ScoringSchema:
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
        "is_disqualified": match.is_disqualified,
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
    raw_scores = match_data.get("raw_scores", {})
    validate_raw_scores(raw_scores, schema_fields)
    total = (
        compute_match_total(raw_scores, schema_fields)
        if raw_scores or schema
        else float(provided_total or 0.0)
    )
    snapshot = None
    if schema:
        snapshot = {"id": schema.id, "version": schema.version, "fields": deepcopy(schema.fields)}

    match = Match(
        **match_data,
        season_id=event.season_id,
        event_id=event.id,
        schema_snapshot=snapshot,
        total_score=total,
        entered_by=entered_by,
    )
    db.add(match)
    await db.flush()
    db.add(_revision(match, entered_by, None))
    await _recompute_ranking(
        db,
        event.id,
        match.team_id,
        match.competition_level_id,
        match.event_phase_id,
    )
    return match


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
    if "raw_scores" in kwargs:
        schema_fields = (match.schema_snapshot or {}).get("fields", [])
        validate_raw_scores(kwargs["raw_scores"], schema_fields)
        kwargs["total_score"] = compute_match_total(kwargs["raw_scores"], schema_fields)
    for key, value in kwargs.items():
        setattr(match, key, value)
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
    return match


async def list_revisions(db: AsyncSession, match_id: str) -> list[ScoreRevision]:
    await get_match(db, match_id)
    result = await db.execute(
        select(ScoreRevision)
        .where(ScoreRevision.match_id == match_id)
        .order_by(ScoreRevision.revision)
    )
    return list(result.scalars().all())


async def confirm_match(db: AsyncSession, match_id: str, confirmed_by: str) -> Match:
    match = await get_match(db, match_id)
    match.confirmed_by = confirmed_by
    match.confirmed_at = datetime.now(UTC)
    return match


async def delete_match(db: AsyncSession, match_id: str) -> None:
    match = await get_match(db, match_id)
    event_id = match.event_id
    team_id = match.team_id
    level_id = match.competition_level_id
    phase_id = match.event_phase_id
    await db.delete(match)
    await db.flush()
    await _recompute_ranking(db, event_id, team_id, level_id, phase_id)


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
    if not await db.get(Event, event_id):
        # Backwards compatibility for callers of the former season-scoped API.
        event_id = (await get_default_event(db, event_id)).id
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
    for rank, ranking in enumerate(result.scalars().all(), start=1):
        ranking.rank = rank


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
