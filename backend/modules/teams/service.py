from datetime import date

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.exceptions import ConflictError, NotFoundError, ValidationError
from modules.seasons.lifecycle import DRAFT, ensure_writable
from modules.teams.models import Team, TeamMember, TeamSeasonMember, TeamSeasonRegistration


async def list_my_teams(db: AsyncSession, user_id: str) -> list[Team]:
    """Teams the given user is a member of (for mentor self-service)."""
    result = await db.execute(
        select(Team)
        .join(TeamMember, TeamMember.team_id == Team.id)
        .where(TeamMember.user_id == user_id)
        .order_by(Team.name)
    )
    return list(result.scalars().unique().all())


def _like_pattern(text: str) -> str:
    """Case-insensitive substring pattern with LIKE wildcards escaped."""
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped.lower()}%"


async def list_teams(
    db: AsyncSession,
    season_id: str | None = None,
    competition_level_id: str | None = None,
    *,
    q: str | None = None,
    country: str | None = None,
    status: str | None = None,
    category: str | None = None,
) -> list[Team]:
    """Teams, optionally searched and filtered.

    ``q`` matches name, team number, school and city (case-insensitive
    substring). ``status`` is ``active`` or ``archived`` (is_active false);
    ``category`` (the season's team type) needs ``season_id``.
    """
    query = select(Team).options(selectinload(Team.members)).order_by(Team.name)
    if season_id:
        query = query.join(TeamSeasonRegistration).where(
            TeamSeasonRegistration.season_id == season_id
        )
        if category:
            query = query.where(TeamSeasonRegistration.category == category)
    if competition_level_id:
        query = query.where(Team.competition_level_id == competition_level_id)
    if q and q.strip():
        pattern = _like_pattern(q.strip())
        query = query.where(
            or_(
                *(
                    func.lower(column).like(pattern, escape="\\")
                    for column in (Team.name, Team.team_number, Team.school, Team.city)
                )
            )
        )
    if country and country.strip():
        query = query.where(func.upper(Team.country) == country.strip().upper())
    if status == "active":
        query = query.where(Team.is_active == True)
    elif status == "archived":
        query = query.where(Team.is_active == False)
    result = await db.execute(query)
    return list(result.scalars().unique().all())


async def list_countries(db: AsyncSession) -> list[str]:
    """Distinct team countries, for the country filter."""
    result = await db.execute(select(Team.country).distinct().order_by(Team.country))
    return [c for c in result.scalars().all() if c]


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


def registration_window_open(season, today: date | None = None) -> bool:
    """Whether ``today`` lies within the season's registration window.

    Unset bounds are open-ended; a season without any window accepts
    registrations at any time (the previous behaviour).
    """
    today = today or date.today()
    if season.registration_open and today < season.registration_open:
        return False
    if season.registration_close and today > season.registration_close:
        return False
    return True


async def register_for_season(
    db: AsyncSession,
    team_id: str,
    season_id: str,
    *,
    enforce_window: bool = False,
    **kwargs,
) -> TeamSeasonRegistration:
    from modules.seasons.models import Season

    season = await db.get(Season, season_id)
    # Mentors cannot see draft seasons, so they cannot register for one either.
    if not season or (enforce_window and season.status == DRAFT):
        raise NotFoundError("Season not found")
    await ensure_writable(db, season_id=season_id)
    if enforce_window and not registration_window_open(season):
        raise ConflictError("Registration for this season is closed")

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
    await ensure_writable(db, season_id=reg.season_id)
    reg.confirmed = True
    return reg


async def delete_registration(db: AsyncSession, registration_id: str) -> None:
    result = await db.execute(
        select(TeamSeasonRegistration).where(TeamSeasonRegistration.id == registration_id)
    )
    reg = result.scalar_one_or_none()
    if not reg:
        raise NotFoundError("Registration not found")
    await ensure_writable(db, season_id=reg.season_id)
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


# ── Season participation details ──────────────────────────────────────────────


async def get_season_registration(
    db: AsyncSession, team_id: str, season_id: str
) -> TeamSeasonRegistration:
    result = await db.execute(
        select(TeamSeasonRegistration).where(
            TeamSeasonRegistration.team_id == team_id,
            TeamSeasonRegistration.season_id == season_id,
        )
    )
    reg = result.scalar_one_or_none()
    if not reg:
        raise NotFoundError("Team is not registered for this season")
    return reg


async def update_season_registration(
    db: AsyncSession, team_id: str, season_id: str, changes: dict
) -> TeamSeasonRegistration:
    """Apply `changes` (already limited to what the caller may edit)."""
    reg = await get_season_registration(db, team_id, season_id)
    await ensure_writable(db, season_id=season_id)
    if changes.get("competition_level_id"):
        from modules.seasons.models import CompetitionLevel

        if not await db.get(CompetitionLevel, changes["competition_level_id"]):
            raise ValidationError("Competition level not found")
    for key, value in changes.items():
        setattr(reg, key, value)
    # Kit shipping only concerns botball teams; an open team has no kit.
    if reg.category != "botball" and "kit_status" not in changes:
        reg.kit_status = "not_sent"
    await db.flush()
    await db.refresh(reg)
    return reg


async def get_season_roster(db: AsyncSession, team_id: str, season_id: str) -> list[dict]:
    reg = await get_season_registration(db, team_id, season_id)
    result = await db.execute(
        select(TeamSeasonMember, TeamMember)
        .join(TeamMember, TeamMember.id == TeamSeasonMember.member_id)
        .where(TeamSeasonMember.registration_id == reg.id)
        .order_by(TeamMember.name)
    )
    return [
        {
            "id": entry.id,
            "member_id": member.id,
            "name": member.name,
            "team_role": member.role,
            "role": entry.role,
        }
        for entry, member in result.all()
    ]


async def set_season_roster(
    db: AsyncSession, team_id: str, season_id: str, entries: list[dict]
) -> list[dict]:
    """Replace the season's roster with `entries` ({member_id, role}).

    Every member must belong to the team; listing a member twice is an error.
    """
    reg = await get_season_registration(db, team_id, season_id)
    await ensure_writable(db, season_id=season_id)
    wanted: dict[str, str | None] = {}
    for entry in entries:
        if entry["member_id"] in wanted:
            raise ValidationError("A member is listed more than once")
        wanted[entry["member_id"]] = (entry.get("role") or "").strip() or None
    if wanted:
        known = set(
            (
                await db.execute(
                    select(TeamMember.id).where(
                        TeamMember.team_id == team_id, TeamMember.id.in_(list(wanted))
                    )
                )
            ).scalars()
        )
        unknown = set(wanted) - known
        if unknown:
            raise ValidationError("Only members of this team can be on its season roster")

    existing = {
        entry.member_id: entry
        for entry in (
            await db.execute(
                select(TeamSeasonMember).where(TeamSeasonMember.registration_id == reg.id)
            )
        ).scalars()
    }
    for member_id, current in existing.items():
        if member_id not in wanted:
            await db.delete(current)
    for member_id, role in wanted.items():
        if member_id in existing:
            existing[member_id].role = role
        else:
            db.add(TeamSeasonMember(registration_id=reg.id, member_id=member_id, role=role))
    await db.flush()
    return await get_season_roster(db, team_id, season_id)


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
