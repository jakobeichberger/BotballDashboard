from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.exceptions import ConflictError, NotFoundError
from modules.seasons.models import CompetitionLevel, Season, SeasonPhase


async def list_seasons(db: AsyncSession) -> list[Season]:
    result = await db.execute(
        select(Season).options(selectinload(Season.phases)).order_by(Season.year.desc())
    )
    return list(result.scalars().all())


async def get_season(db: AsyncSession, season_id: str) -> Season:
    result = await db.execute(
        select(Season).where(Season.id == season_id).options(selectinload(Season.phases))
    )
    season = result.scalar_one_or_none()
    if not season:
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


async def create_season(db: AsyncSession, data: dict, phases: list[dict]) -> Season:
    from modules.events.models import Event, EventPhase

    season = Season(**data)
    db.add(season)
    await db.flush()

    event = Event(
        season_id=season.id,
        name=f"{season.name} – Main Event",
        slug=f"season-{season.year}-{season.id[:8]}",
        status="draft",
        active_modules=["seeding"],
    )
    db.add(event)
    await db.flush()

    for sort_order, phase_data in enumerate(phases):
        db.add(SeasonPhase(season_id=season.id, **phase_data))
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
    # At most one season may be active. A PATCH setting is_active=True has to go
    # through the same deactivate-all step as set_active_season, otherwise it
    # silently creates a second active season and breaks GET /seasons/active.
    if kwargs.get("is_active") is True:
        await db.execute(update(Season).values(is_active=False))
    for key, value in kwargs.items():
        if value is not None:
            setattr(season, key, value)
    return season


async def set_active_season(db: AsyncSession, season_id: str) -> Season:
    # Deactivate all
    await db.execute(update(Season).values(is_active=False))
    season = await get_season(db, season_id)
    season.is_active = True
    return season


async def delete_season(db: AsyncSession, season_id: str) -> None:
    season = await get_season(db, season_id)
    if season.is_active:
        raise ConflictError("Cannot delete active season")
    await db.delete(season)


async def activate_phase(db: AsyncSession, season_id: str, phase_id: str) -> SeasonPhase:
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


async def list_competition_levels(db: AsyncSession) -> list[CompetitionLevel]:
    result = await db.execute(
        select(CompetitionLevel)
        .where(CompetitionLevel.is_active == True)
        .order_by(CompetitionLevel.name)
    )
    return list(result.scalars().all())
