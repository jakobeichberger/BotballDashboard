"""Team-addressed notifications around the tournament schedule.

Everything here only queues outbox rows (``core.domain_events.emit_event``);
the notification worker delivers them after the transaction has committed.
Reminders carry a ``dedupe_key`` so the periodic tasks that queue them can run
as often as they like without anyone being notified twice.
"""

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.domain_events import emit_event
from modules.auth.models import User
from modules.events.models import Event, MatchParticipant, ScheduledMatch
from modules.seasons.models import SeasonEvent
from modules.teams.models import Team, TeamMember, TeamSeasonRegistration

MATCH_REMINDER_MINUTES = 10
DEADLINE_REMINDER_DAYS = (7, 3, 1)


async def team_member_user_ids(db: AsyncSession, team_ids: list[str]) -> list[str]:
    """Accounts linked to the members (incl. mentors) of the given teams."""
    if not team_ids:
        return []
    result = await db.execute(
        select(TeamMember.user_id).where(
            TeamMember.team_id.in_(team_ids), TeamMember.user_id.isnot(None)
        )
    )
    return sorted({str(user_id) for user_id in result.scalars()})


async def team_member_emails(db: AsyncSession, team_ids: list[str]) -> list[str]:
    """E-mail addresses of team members: the member entry, else the linked account."""
    if not team_ids:
        return []
    result = await db.execute(
        select(TeamMember.email, User.email)
        .outerjoin(User, User.id == TeamMember.user_id)
        .where(TeamMember.team_id.in_(team_ids))
    )
    return sorted({member or account for member, account in result.all() if member or account})


def _participant_team_ids(match: ScheduledMatch) -> list[str]:
    return [str(p.team_id) for p in match.participants if p.team_id]


async def queue_match_reminders(db: AsyncSession, now: datetime | None = None) -> int:
    """Queue "match starts soon" pushes for matches starting within 10 minutes.

    Each match is announced once (dedupe key per match), to the members of the
    teams playing it. Returns the number of reminders queued.
    """
    now = now or datetime.now(UTC)
    result = await db.execute(
        select(ScheduledMatch)
        .options(selectinload(ScheduledMatch.participants).selectinload(MatchParticipant.team))
        .where(
            ScheduledMatch.status.in_(("scheduled", "called")),
            ScheduledMatch.scheduled_at.isnot(None),
            ScheduledMatch.scheduled_at > now,
            ScheduledMatch.scheduled_at <= now + timedelta(minutes=MATCH_REMINDER_MINUTES),
        )
    )
    queued = 0
    for match in result.scalars():
        team_ids = _participant_team_ids(match)
        user_ids = await team_member_user_ids(db, team_ids)
        if not user_ids:
            continue
        starts_at = match.scheduled_at
        if starts_at is not None and starts_at.tzinfo is None:
            starts_at = starts_at.replace(tzinfo=UTC)
        minutes = max(1, round(((starts_at or now) - now).total_seconds() / 60))
        teams = " vs. ".join(p.team_name or "TBD" for p in match.participants) or "TBD"
        table = f", table {match.table_number}" if match.table_number else ""
        item = await emit_event(
            db,
            "match_starting_soon",
            event_id=match.event_id,
            payload={
                "title": f"Match {match.code} starts soon",
                "message": f"{teams} starts in about {minutes} min{table}.",
                "matchId": match.id,
                "userIds": user_ids,
                "url": f"/events/{match.event_id}/schedule",
            },
            dedupe_key=f"match-soon:{match.id}",
        )
        queued += item is not None
    return queued


async def queue_deadline_reminders(db: AsyncSession, today: date | None = None) -> int:
    """Queue reminders for season deadlines due in 7, 3 and 1 day(s).

    Recipients are the members of every team registered for the season: a
    push to linked accounts and, where e-mail is configured, a mail to all
    known member addresses. Returns the number of reminders queued.
    """
    today = today or datetime.now(UTC).date()
    due_dates = {today + timedelta(days=days): days for days in DEADLINE_REMINDER_DAYS}
    result = await db.execute(
        select(SeasonEvent).where(
            SeasonEvent.event_type == "deadline",
            SeasonEvent.event_date.in_(list(due_dates)),
        )
    )
    queued = 0
    for deadline in result.scalars():
        days = due_dates[deadline.event_date]
        registrations = await db.execute(
            select(TeamSeasonRegistration.team_id).where(
                TeamSeasonRegistration.season_id == deadline.season_id
            )
        )
        team_ids = [str(team_id) for team_id in registrations.scalars()]
        user_ids = await team_member_user_ids(db, team_ids)
        emails = await team_member_emails(db, team_ids)
        if not user_ids and not emails:
            continue
        when = "tomorrow" if days == 1 else f"in {days} days"
        message = f"{deadline.title} is due {when} ({deadline.event_date.isoformat()})."
        if deadline.description:
            message += f"\n\n{deadline.description}"
        item = await emit_event(
            db,
            "deadline_reminder",
            payload={
                "title": f"Deadline {when}: {deadline.title}",
                "message": message,
                "userIds": user_ids,
                "emails": emails,
                "url": "/",
            },
            dedupe_key=f"deadline:{deadline.id}:{deadline.event_date.isoformat()}:{days}",
        )
        queued += item is not None
    return queued


async def notify_score_corrected(
    db: AsyncSession, event_id: str | None, team_id: str, match_id: str, round_number: int
) -> None:
    """Tell a team's members that one of their official scores was corrected."""
    user_ids = await team_member_user_ids(db, [team_id])
    if not user_ids:
        return
    team = await db.get(Team, team_id)
    await emit_event(
        db,
        "score_corrected",
        event_id=event_id,
        payload={
            "title": "Score corrected",
            "message": (
                f"The round {round_number} score of {team.name if team else 'your team'} "
                "was corrected."
            ),
            "matchId": match_id,
            "userIds": user_ids,
        },
    )


async def notify_result_corrected(db: AsyncSession, event_id: str, match: ScheduledMatch) -> None:
    """Tell both teams that the recorded result of a scheduled match changed."""
    team_ids = _participant_team_ids(match)
    user_ids = await team_member_user_ids(db, team_ids)
    if not user_ids:
        return
    event = await db.get(Event, event_id)
    await emit_event(
        db,
        "score_corrected",
        event_id=event_id,
        payload={
            "title": "Result corrected",
            "message": f"The result of match {match.code}"
            + (f" at {event.name}" if event else "")
            + " was corrected.",
            "matchId": match.id,
            "userIds": user_ids,
        },
    )
