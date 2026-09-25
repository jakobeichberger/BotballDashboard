from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.exceptions import ConflictError, NotFoundError, ValidationError
from modules.seasons.lifecycle import (
    ARCHIVED,
    ARCHIVED_SEASON_MESSAGE,
    DRAFT,
    ensure_writable,
    season_has_data,
)
from modules.seasons.models import CompetitionLevel, Season, SeasonEvent, SeasonPhase


async def list_seasons(db: AsyncSession, include_drafts: bool = True) -> list[Season]:
    query = select(Season).options(selectinload(Season.phases)).order_by(Season.year.desc())
    if not include_drafts:
        query = query.where(Season.status != DRAFT)
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_season(db: AsyncSession, season_id: str, include_drafts: bool = True) -> Season:
    result = await db.execute(
        select(Season).where(Season.id == season_id).options(selectinload(Season.phases))
    )
    season = result.scalar_one_or_none()
    # A draft is invisible to users who may not edit seasons: same 404 as a
    # season that does not exist, so its existence is not disclosed either.
    if not season or (season.status == DRAFT and not include_drafts):
        raise NotFoundError("Season not found")
    return season


async def get_active_season(db: AsyncSession) -> Season | None:
    # .first() rather than .scalar_one_or_none(): if the data ever ends up with
    # more than one active season this endpoint should still answer instead of
    # failing permanently with MultipleResultsFound.
    result = await db.execute(
        select(Season)
        .where(Season.is_active.is_(True))
        .options(selectinload(Season.phases))
        .order_by(Season.year.desc())
        .limit(1)
    )
    return result.scalars().first()


async def _deactivate_other_seasons(db: AsyncSession, season_id: str | None) -> None:
    """At most one season is active; the one being replaced counts as finished."""
    others = update(Season).where(Season.is_active.is_(True))
    if season_id:
        others = others.where(Season.id != season_id)
    await db.execute(others.values(is_active=False))
    finished = update(Season).where(Season.status == "active")
    if season_id:
        finished = finished.where(Season.id != season_id)
    await db.execute(finished.values(status="finished"))


async def _apply_status(db: AsyncSession, season: Season, status: str) -> None:
    if status == "active":
        await _deactivate_other_seasons(db, season.id)
        season.is_active = True
    else:
        season.is_active = False
    season.status = status


async def create_season(
    db: AsyncSession,
    data: dict,
    phases: list[dict],
    create_default_event: bool = True,
) -> Season:
    from modules.events.models import Event, EventPhase
    from modules.events.module_access import modules_for_season

    is_active = bool(data.pop("is_active", False))
    status = data.pop("status", None) or ("active" if is_active else DRAFT)
    if is_active or status == "active":
        # Same deactivate-all step as set_active_season. Without it the setup
        # wizard's "is_active: true" was silently dropped and /seasons/active
        # kept pointing at the old season.
        await _deactivate_other_seasons(db, None)
        is_active, status = True, "active"

    season = Season(**data, is_active=is_active, status=status)
    db.add(season)
    await db.flush()

    event = None
    if create_default_event:
        event = Event(
            season_id=season.id,
            name=f"{season.name} – Main Event",
            slug=f"season-{season.year}-{season.id[:8]}",
            status="draft",
            active_modules=modules_for_season(season),
        )
        db.add(event)
        await db.flush()

    for sort_order, phase_data in enumerate(phases):
        db.add(SeasonPhase(season_id=season.id, **phase_data))
        if event is not None:
            db.add(
                EventPhase(
                    event_id=event.id,
                    name=phase_data["name"],
                    phase_type="seeding",
                    sort_order=sort_order,
                    status="live" if phase_data.get("is_active") else "draft",
                )
            )

    # The phases are still pending, and autoflush is off — without this the
    # refresh re-SELECTs and the response reports no phases at all.
    await db.flush()
    await db.refresh(season, ["phases"])
    return season


async def update_season(db: AsyncSession, season_id: str, **kwargs) -> Season:
    season = await get_season(db, season_id)
    status = kwargs.pop("status", None)
    is_active = kwargs.pop("is_active", None)
    changes = {key: value for key, value in kwargs.items() if value is not None}

    if season.status == ARCHIVED and changes:
        # Only the lifecycle itself may change: un-archive first, then edit.
        raise ConflictError(ARCHIVED_SEASON_MESSAGE)

    # At most one season may be active. A PATCH setting is_active=True has to go
    # through the same deactivate-all step as set_active_season, otherwise it
    # silently creates a second active season and breaks GET /seasons/active.
    if status is None and is_active is not None:
        if is_active:
            status = "active"
        elif season.status == "active":
            status = "finished"
    if status is not None:
        await _apply_status(db, season, status)

    for key, value in changes.items():
        setattr(season, key, value)
    return season


async def set_active_season(db: AsyncSession, season_id: str) -> Season:
    season = await get_season(db, season_id)
    await _apply_status(db, season, "active")
    return season


async def delete_season(db: AsyncSession, season_id: str) -> None:
    season = await get_season(db, season_id)
    if season.is_active:
        raise ConflictError("Cannot delete active season")
    # Deleting cascades through every table that references the season, score
    # revisions included. Tournament history must be archived, not deleted.
    if await season_has_data(db, season_id):
        raise ConflictError(
            "Season has registrations, matches, results, papers or print jobs; "
            "archive it instead of deleting it"
        )
    await db.delete(season)
    await db.flush()


async def activate_phase(db: AsyncSession, season_id: str, phase_id: str) -> SeasonPhase:
    await ensure_writable(db, season_id=season_id)
    # Deactivate all phases in this season
    result = await db.execute(select(SeasonPhase).where(SeasonPhase.season_id == season_id))
    for existing_phase in result.scalars().all():
        existing_phase.is_active = False

    result = await db.execute(
        select(SeasonPhase).where(SeasonPhase.id == phase_id, SeasonPhase.season_id == season_id)
    )
    selected_phase = result.scalar_one_or_none()
    if not selected_phase:
        raise NotFoundError("Phase not found")
    selected_phase.is_active = True
    return selected_phase


async def list_competition_levels(
    db: AsyncSession, include_inactive: bool = False
) -> list[CompetitionLevel]:
    q = select(CompetitionLevel).order_by(CompetitionLevel.order, CompetitionLevel.name)
    if not include_inactive:
        q = q.where(CompetitionLevel.is_active == True)
    result = await db.execute(q)
    return list(result.scalars().all())


async def create_competition_level(db: AsyncSession, data: dict) -> CompetitionLevel:
    existing = await db.execute(
        select(CompetitionLevel).where(CompetitionLevel.code == data["code"])
    )
    if existing.scalar_one_or_none():
        raise ConflictError("Competition level code already exists")
    level = CompetitionLevel(**data)
    await _check_qualification_source(db, level, data.get("qualifies_from_level_id"))
    db.add(level)
    await db.flush()
    return level


async def _check_qualification_source(
    db: AsyncSession, level: CompetitionLevel, source_id: str | None
) -> None:
    """The level teams qualify from must exist and must not lead back to `level`."""
    seen = {level.id} if level.id else set()
    current = source_id
    while current:
        if current in seen:
            raise ValidationError("A level cannot (indirectly) qualify from itself")
        seen.add(current)
        source = await db.get(CompetitionLevel, current)
        if not source:
            raise NotFoundError("Qualification source level not found")
        current = source.qualifies_from_level_id


async def update_competition_level(db: AsyncSession, level_id: str, **kwargs) -> CompetitionLevel:
    result = await db.execute(select(CompetitionLevel).where(CompetitionLevel.id == level_id))
    level = result.scalar_one_or_none()
    if not level:
        raise NotFoundError("Competition level not found")
    if "qualifies_from_level_id" in kwargs:
        await _check_qualification_source(db, level, kwargs["qualifies_from_level_id"])
        level.qualifies_from_level_id = kwargs.pop("qualifies_from_level_id")
    for key, value in kwargs.items():
        if value is not None:
            setattr(level, key, value)
    return level


async def delete_competition_level(db: AsyncSession, level_id: str) -> None:
    result = await db.execute(select(CompetitionLevel).where(CompetitionLevel.id == level_id))
    level = result.scalar_one_or_none()
    if not level:
        raise NotFoundError("Competition level not found")
    await db.delete(level)


# ── Season events / deadlines ──────────────────────────────────────────────────


async def list_events(db: AsyncSession, season_id: str) -> list[SeasonEvent]:
    result = await db.execute(
        select(SeasonEvent)
        .where(SeasonEvent.season_id == season_id)
        .order_by(SeasonEvent.event_date)
    )
    return list(result.scalars().all())


async def create_event(db: AsyncSession, season_id: str, data: dict) -> SeasonEvent:
    await get_season(db, season_id)  # validate season exists
    await ensure_writable(db, season_id=season_id)
    event = SeasonEvent(season_id=season_id, **data)
    db.add(event)
    await db.flush()
    return event


async def delete_event(db: AsyncSession, season_id: str, event_id: str) -> None:
    await ensure_writable(db, season_id=season_id)
    result = await db.execute(
        select(SeasonEvent).where(
            SeasonEvent.id == event_id,
            SeasonEvent.season_id == season_id,  # scope to the season in the path
        )
    )
    event = result.scalar_one_or_none()
    if not event:
        raise NotFoundError("Event not found")
    await db.delete(event)
