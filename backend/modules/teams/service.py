from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.exceptions import ConflictError, NotFoundError
from modules.teams.models import Team, TeamMember, TeamSeasonRegistration


async def list_teams(
    db: AsyncSession,
    season_id: str | None = None,
    competition_level_id: str | None = None,
) -> list[Team]:
    q = select(Team).options(selectinload(Team.members)).order_by(Team.name)
    if season_id:
        q = q.join(TeamSeasonRegistration).where(TeamSeasonRegistration.season_id == season_id)
    if competition_level_id:
        q = q.where(Team.competition_level_id == competition_level_id)
    result = await db.execute(q)
    return list(result.scalars().unique().all())


async def get_team(db: AsyncSession, team_id: str) -> Team:
    result = await db.execute(
        select(Team).where(Team.id == team_id).options(selectinload(Team.members))
    )
    team = result.scalar_one_or_none()
    if not team:
        raise NotFoundError("Team not found")
    return team


async def create_team(db: AsyncSession, data: dict, members: list[dict]) -> Team:
    team = Team(**data)
    db.add(team)
    await db.flush()

    for member_data in members:
        db.add(TeamMember(team_id=team.id, **member_data))

    await db.refresh(team, ["members"])
    return team


async def update_team(db: AsyncSession, team_id: str, **kwargs) -> Team:
    team = await get_team(db, team_id)
    for key, value in kwargs.items():
        if value is not None:
            setattr(team, key, value)
    return team


async def delete_team(db: AsyncSession, team_id: str) -> None:
    team = await get_team(db, team_id)
    await db.delete(team)


async def add_member(db: AsyncSession, team_id: str, member_data: dict) -> TeamMember:
    await get_team(db, team_id)  # validate exists
    member = TeamMember(team_id=team_id, **member_data)
    db.add(member)
    return member


async def remove_member(db: AsyncSession, team_id: str, member_id: str) -> None:
    result = await db.execute(
        select(TeamMember).where(TeamMember.id == member_id, TeamMember.team_id == team_id)
    )
    member = result.scalar_one_or_none()
    if not member:
        raise NotFoundError("Team member not found")
    await db.delete(member)


async def register_for_season(db: AsyncSession, team_id: str, season_id: str, **kwargs) -> TeamSeasonRegistration:
    existing = await db.execute(
        select(TeamSeasonRegistration).where(
            TeamSeasonRegistration.team_id == team_id,
            TeamSeasonRegistration.season_id == season_id,
        )
    )
    if existing.scalar_one_or_none():
        raise ConflictError("Team already registered for this season")

    reg = TeamSeasonRegistration(team_id=team_id, season_id=season_id, **kwargs)
    db.add(reg)
    return reg


async def confirm_registration(db: AsyncSession, registration_id: str) -> TeamSeasonRegistration:
    result = await db.execute(
        select(TeamSeasonRegistration).where(TeamSeasonRegistration.id == registration_id)
    )
    reg = result.scalar_one_or_none()
    if not reg:
        raise NotFoundError("Registration not found")
    reg.confirmed = True
    return reg


async def list_registrations(
    db: AsyncSession, season_id: str | None = None, team_id: str | None = None
) -> list[TeamSeasonRegistration]:
    q = select(TeamSeasonRegistration)
    if season_id:
        q = q.where(TeamSeasonRegistration.season_id == season_id)
    if team_id:
        q = q.where(TeamSeasonRegistration.team_id == team_id)
    result = await db.execute(q)
    return list(result.scalars().all())
