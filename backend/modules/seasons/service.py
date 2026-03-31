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
    result = await db.execute(
        select(Season).where(Season.is_active == True).options(selectinload(Season.phases))
    )
    return result.scalar_one_or_none()


async def create_season(db: AsyncSession, data: dict, phases: list[dict]) -> Season:
    season = Season(**data)
    db.add(season)
    await db.flush()

    for phase_data in phases:
        db.add(SeasonPhase(season_id=season.id, **phase_data))

    await db.refresh(season, ["phases"])
    return season


async def update_season(db: AsyncSession, season_id: str, **kwargs) -> Season:
    season = await get_season(db, season_id)
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
    result = await db.execute(
        select(SeasonPhase).where(SeasonPhase.season_id == season_id)
    )
    for phase in result.scalars().all():
        phase.is_active = False

    result = await db.execute(
        select(SeasonPhase).where(SeasonPhase.id == phase_id, SeasonPhase.season_id == season_id)
    )
    phase = result.scalar_one_or_none()
    if not phase:
        raise NotFoundError("Phase not found")
    phase.is_active = True
    return phase


async def list_competition_levels(db: AsyncSession) -> list[CompetitionLevel]:
    result = await db.execute(
        select(CompetitionLevel).where(CompetitionLevel.is_active == True).order_by(CompetitionLevel.name)
    )
    return list(result.scalars().all())
