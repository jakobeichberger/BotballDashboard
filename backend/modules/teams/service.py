from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.exceptions import ConflictError, NotFoundError, ValidationError
from modules.teams.models import Team, TeamMember, TeamSeasonRegistration


async def list_my_teams(db: AsyncSession, user_id: str) -> list[Team]:
    """Teams the given user is a member of (for mentor self-service)."""
    result = await db.execute(
        select(Team)
        .join(TeamMember, TeamMember.team_id == Team.id)
        .where(TeamMember.user_id == user_id)
        .order_by(Team.name)
    )
    return list(result.scalars().unique().all())


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
        setattr(team, key, value)
    return team


async def delete_team(db: AsyncSession, team_id: str) -> None:
    team = await get_team(db, team_id)
    await db.delete(team)


async def add_member(db: AsyncSession, team_id: str, member_data: dict) -> TeamMember:
    await get_team(db, team_id)  # validate exists
    member = TeamMember(team_id=team_id, **member_data)
    db.add(member)
    await db.flush()
    await db.refresh(member)
    return member


async def update_member(
    db: AsyncSession, team_id: str, member_id: str, changes: dict
) -> TeamMember:
    """Apply `changes` to a member. Linking a user account (user_id) is what
    gives a mentor access to the team, so the account must exist, be active
    and not already be linked to another member of the same team."""
    result = await db.execute(
        select(TeamMember).where(TeamMember.id == member_id, TeamMember.team_id == team_id)
    )
    member = result.scalar_one_or_none()
    if not member:
        raise NotFoundError("Team member not found")

    for key in ("name", "role"):
        if key in changes and changes[key] is None:
            raise ValidationError(f"{key} must not be empty")
    user_id = changes.get("user_id")
    if user_id:
        from modules.auth.models import User

        user = await db.get(User, user_id)
        if not user or not user.is_active:
            raise ValidationError("User account not found or inactive")
        duplicate = await db.execute(
            select(TeamMember.id).where(
                TeamMember.team_id == team_id,
                TeamMember.user_id == user_id,
                TeamMember.id != member_id,
            )
        )
        if duplicate.scalar_one_or_none():
            raise ConflictError("This account is already linked to another member of the team")

    for key, value in changes.items():
        setattr(member, key, value)
    await db.flush()
    await db.refresh(member)
    return member


async def remove_member(db: AsyncSession, team_id: str, member_id: str) -> None:
    result = await db.execute(
        select(TeamMember).where(TeamMember.id == member_id, TeamMember.team_id == team_id)
    )
    member = result.scalar_one_or_none()
    if not member:
        raise NotFoundError("Team member not found")
    await db.delete(member)


async def register_for_season(
    db: AsyncSession, team_id: str, season_id: str, **kwargs
) -> TeamSeasonRegistration:
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
    await db.flush()
    await db.refresh(reg)
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


async def delete_registration(db: AsyncSession, registration_id: str) -> None:
    result = await db.execute(
        select(TeamSeasonRegistration).where(TeamSeasonRegistration.id == registration_id)
    )
    reg = result.scalar_one_or_none()
    if not reg:
        raise NotFoundError("Registration not found")
    await db.delete(reg)


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


async def get_team_history(db: AsyncSession, team_id: str) -> list[dict]:
    """Return cross-season event outcomes without exposing team-member data."""
    from modules.events.models import Event, EventRegistration
    from modules.scoring.models import Ranking
    from modules.seasons.models import Season

    await get_team(db, team_id)
    result = await db.execute(
        select(EventRegistration, Event, Season, Ranking)
        .join(Event, Event.id == EventRegistration.event_id)
        .join(Season, Season.id == Event.season_id)
        .outerjoin(
            Ranking,
            (Ranking.event_id == Event.id)
            & (Ranking.team_id == EventRegistration.team_id)
            & Ranking.event_phase_id.is_(None),
        )
        .where(EventRegistration.team_id == team_id)
        .order_by(Season.year.desc(), Event.starts_at.desc().nullslast())
    )
    return [
        {
            "event_id": event.id,
            "event_name": event.name,
            "season_id": season.id,
            "season_name": season.name,
            "season_year": season.year,
            "category": registration.category,
            "rank": ranking.rank if ranking else None,
            "seed_score": ranking.seed_score if ranking else None,
            "best_score": ranking.best_score if ranking else None,
            "rounds_played": ranking.rounds_played if ranking else 0,
        }
        for registration, event, season, ranking in result.all()
    ]
