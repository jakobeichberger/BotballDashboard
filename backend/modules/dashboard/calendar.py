"""Deadline calendar, season timeline and the per-user iCal feed.

Deadlines are collected from where they already live — season dates, events
and their phases, custom season entries and a reviewer's own assignments — so
there is no second place to keep them in sync.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import has_elevated_access, own_team_ids
from modules.dashboard.models import CalendarFeedToken
from modules.events.models import Event, EventPhase, EventRegistration
from modules.paper_review.models import Paper, ReviewerAssignment
from modules.seasons.models import Season, SeasonEvent
from modules.teams.models import TeamSeasonRegistration

#: Permissions that make someone an organizer for calendar purposes: they see
#: draft events and every season, not just their own.
ORGANIZER_PERMISSIONS = (
    "seasons:write",
    "events:write",
    "scoring:admin",
    "papers:admin",
    "printing:admin",
    "teams:admin",
    "dashboard:write",
)

#: Colour per deadline kind, as specified for the deadline calendar (module 08).
KIND_COLORS = {
    "paper": "red",
    "review": "orange",
    "printing": "green",
    "registration": "gray",
    "competition": "blue",
    "event": "blue",
    "phase": "blue",
    "deadline": "orange",
    "milestone": "blue",
}

_SUBMITTED_PAPER_STATUSES = {
    "submitted",
    "under_review",
    "accepted",
    "rejected",
    "revision_requested",
}


# ── Scope ─────────────────────────────────────────────────────────────────────


async def is_organizer(db: AsyncSession, user) -> bool:
    return await has_elevated_access(db, user, ORGANIZER_PERMISSIONS)


async def relevant_season_ids(db: AsyncSession, user) -> set[str]:
    """Seasons whose deadlines concern `user` when no season is chosen.

    Everyone gets the active season(s) — a mentor whose team is not registered
    yet still needs the registration deadline. Team members additionally get
    every season their team is registered for, per season or per event.
    """
    active = await db.execute(select(Season.id).where(Season.is_active.is_(True)))
    ids = set(active.scalars().all())
    team_ids = await own_team_ids(db, user)
    if team_ids:
        registered = await db.execute(
            select(TeamSeasonRegistration.season_id).where(
                TeamSeasonRegistration.team_id.in_(team_ids)
            )
        )
        ids |= set(registered.scalars().all())
        via_events = await db.execute(
            select(Event.season_id)
            .join(EventRegistration, EventRegistration.event_id == Event.id)
            .where(EventRegistration.team_id.in_(team_ids))
        )
        ids |= set(via_events.scalars().all())
    return ids


# ── Collection ────────────────────────────────────────────────────────────────


def _event_color(event: Event) -> str:
    text = f"{event.event_type} {event.name}".lower()
    return "purple" if "gcer" in text or "global" in text else "blue"


def _entry(
    uid: str,
    title: str,
    kind: str,
    start: date | datetime,
    season: Season,
    *,
    end: date | datetime | None = None,
    color: str | None = None,
    event_id: str | None = None,
    description: str | None = None,
    done: bool | None = None,
) -> dict[str, Any]:
    return {
        "id": uid,
        "title": title,
        "kind": kind,
        "color": color or KIND_COLORS.get(kind, "gray"),
        "start": start,
        "end": end,
        "all_day": not isinstance(start, datetime),
        "season_id": season.id,
        "season_name": season.name,
        "event_id": event_id,
        "description": description,
        "done": done,
    }


def _sort_key(entry: dict[str, Any]) -> datetime:
    start = entry["start"]
    if isinstance(start, datetime):
        return start if start.tzinfo else start.replace(tzinfo=UTC)
    return datetime.combine(start, time.min, tzinfo=UTC)


async def collect_deadlines(
    db: AsyncSession,
    user,
    season_ids: set[str],
    *,
    since: date | None = None,
) -> list[dict[str, Any]]:
    """Every dated entry of the given seasons that concerns `user`."""
    if not season_ids:
        return []
    organizer = await is_organizer(db, user)
    team_ids = await own_team_ids(db, user)
    seasons = list(
        (await db.execute(select(Season).where(Season.id.in_(season_ids)))).scalars().all()
    )
    by_id = {s.id: s for s in seasons}
    entries: list[dict[str, Any]] = []

    submitted_seasons: set[str] = set()
    if team_ids:
        papers = await db.execute(
            select(Paper.season_id, Paper.status).where(
                Paper.team_id.in_(team_ids), Paper.season_id.in_(season_ids)
            )
        )
        submitted_seasons = {r.season_id for r in papers if r.status in _SUBMITTED_PAPER_STATUSES}

    for s in seasons:
        if s.registration_open:
            entries.append(
                _entry(
                    f"season-{s.id}-registration-open",
                    "Anmeldung öffnet",
                    "registration",
                    s.registration_open,
                    s,
                )
            )
        if s.registration_close:
            entries.append(
                _entry(
                    f"season-{s.id}-registration-close",
                    "Anmeldeschluss",
                    "registration",
                    s.registration_close,
                    s,
                )
            )
        if s.paper_submission_deadline:
            entries.append(
                _entry(
                    f"season-{s.id}-paper",
                    "Paper-Einreichung",
                    "paper",
                    s.paper_submission_deadline,
                    s,
                    done=(s.id in submitted_seasons) if team_ids else None,
                )
            )
        if s.print_submission_deadline:
            entries.append(
                _entry(
                    f"season-{s.id}-printing",
                    "Druckjob-Deadline",
                    "printing",
                    s.print_submission_deadline,
                    s,
                )
            )
        if s.event_start:
            entries.append(
                _entry(
                    f"season-{s.id}-competition",
                    f"Wettbewerb {s.name}",
                    "competition",
                    s.event_start,
                    s,
                    end=s.event_end,
                )
            )

    custom = await db.execute(select(SeasonEvent).where(SeasonEvent.season_id.in_(season_ids)))
    for item in custom.scalars():
        kind = "deadline" if item.event_type == "deadline" else "milestone"
        color = "orange" if kind == "deadline" else "blue"
        if "paper" in item.title.lower():
            color = "red" if "offiziell" in item.title.lower() else "orange"
        entries.append(
            _entry(
                f"season-event-{item.id}",
                item.title,
                kind,
                item.event_date,
                by_id[item.season_id],
                color=color,
                description=item.description,
            )
        )

    event_query = select(Event).where(Event.season_id.in_(season_ids))
    if not organizer:
        # Drafts are internal planning, not a date anyone should put in a calendar.
        event_query = event_query.where(Event.status != "draft")
    events = list((await db.execute(event_query)).scalars().all())
    for event in events:
        season = by_id[event.season_id]
        color = _event_color(event)
        if event.starts_at:
            entries.append(
                _entry(
                    f"event-{event.id}",
                    event.name,
                    "event",
                    event.starts_at,
                    season,
                    end=event.ends_at,
                    color=color,
                    event_id=event.id,
                    description=event.venue,
                )
            )
    if events:
        phases = await db.execute(
            select(EventPhase).where(EventPhase.event_id.in_([e.id for e in events]))
        )
        event_by_id = {e.id: e for e in events}
        for phase in phases.scalars():
            if not phase.starts_at:
                continue
            event = event_by_id[phase.event_id]
            entries.append(
                _entry(
                    f"phase-{phase.id}",
                    f"{event.name}: {phase.name}",
                    "phase",
                    phase.starts_at,
                    by_id[event.season_id],
                    end=phase.ends_at,
                    color=_event_color(event),
                    event_id=event.id,
                )
            )

    # A reviewer's own review due dates.
    assignments = await db.execute(
        select(ReviewerAssignment, Paper)
        .join(Paper, Paper.id == ReviewerAssignment.paper_id)
        .where(
            ReviewerAssignment.reviewer_id == user.id,
            ReviewerAssignment.due_at.isnot(None),
            Paper.season_id.in_(season_ids),
        )
    )
    for assignment, paper in assignments.all():
        if assignment.due_at is None:  # excluded by the query; narrows the type
            continue
        entries.append(
            _entry(
                f"review-{assignment.id}",
                f"Review fällig: {paper.title}",
                "review",
                assignment.due_at,
                by_id[paper.season_id],
                done=assignment.completed_at is not None,
            )
        )

    if since:
        cutoff = datetime.combine(since, time.min, tzinfo=UTC)
        entries = [e for e in entries if _sort_key({"start": e["end"] or e["start"]}) >= cutoff]
    entries.sort(key=_sort_key)
    return entries


def upcoming(entries: list[dict[str, Any]], limit: int = 5) -> list[dict[str, Any]]:
    """The next `limit` entries that have not passed yet."""
    now = datetime.now(UTC)
    today = datetime.combine(now.date(), time.min, tzinfo=UTC)
    return [
        e
        for e in entries
        if _sort_key({"start": e["end"] or e["start"]}) >= (today if e["all_day"] else now)
    ][:limit]


# ── Season timeline ───────────────────────────────────────────────────────────


def _status(starts: datetime | None, ends: datetime | None, stored: str | None) -> str:
    if stored in ("completed", "finished", "archived"):
        return "finished"
    if stored in ("live", "active"):
        return "active"
    now = datetime.now(UTC)

    def aware(value: datetime) -> datetime:
        return value if value.tzinfo else value.replace(tzinfo=UTC)

    if ends and aware(ends) < now:
        return "finished"
    if starts and aware(starts) <= now and (ends is None or aware(ends) >= now):
        return "active"
    return "planned"


async def season_timeline(db: AsyncSession, user, season: Season) -> dict[str, Any]:
    organizer = await is_organizer(db, user)
    query = select(Event).where(Event.season_id == season.id)
    if not organizer:
        query = query.where(Event.status != "draft")
    events = list((await db.execute(query)).scalars().all())
    phases_by_event: dict[str, list[EventPhase]] = {}
    if events:
        result = await db.execute(
            select(EventPhase)
            .where(EventPhase.event_id.in_([e.id for e in events]))
            .order_by(EventPhase.sort_order)
        )
        for phase in result.scalars():
            phases_by_event.setdefault(phase.event_id, []).append(phase)

    def event_sort(e: Event) -> tuple[bool, datetime]:
        if not e.starts_at:
            return True, datetime.max.replace(tzinfo=UTC)
        return False, e.starts_at if e.starts_at.tzinfo else e.starts_at.replace(tzinfo=UTC)

    return {
        "season_id": season.id,
        "season_name": season.name,
        "season_year": season.year,
        "events": [
            {
                "id": e.id,
                "name": e.name,
                "event_type": e.event_type,
                "color": _event_color(e),
                "starts_at": e.starts_at,
                "ends_at": e.ends_at,
                "status": _status(e.starts_at, e.ends_at, e.status),
                "phases": [
                    {
                        "id": p.id,
                        "name": p.name,
                        "phase_type": p.phase_type,
                        "starts_at": p.starts_at,
                        "ends_at": p.ends_at,
                        "status": _status(p.starts_at, p.ends_at, p.status),
                    }
                    for p in phases_by_event.get(e.id, [])
                ],
            }
            for e in sorted(events, key=event_sort)
        ],
    }


# ── iCal ──────────────────────────────────────────────────────────────────────


def _ics_escape(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )


def _fold(line: str) -> str:
    """Fold a content line at 75 octets (RFC 5545 §3.1) without splitting a
    UTF-8 sequence."""
    out: list[str] = []
    current = ""
    for char in line:
        limit = 75 if not out else 74  # continuation lines start with a space
        if len((current + char).encode("utf-8")) > limit:
            out.append(current)
            current = char
        else:
            current += char
    out.append(current)
    return "\r\n ".join(out)


def _ics_datetime(value: datetime) -> str:
    aware = value if value.tzinfo else value.replace(tzinfo=UTC)
    return aware.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def render_ics(entries: list[dict[str, Any]], calendar_name: str = "Botball Deadlines") -> str:
    stamp = _ics_datetime(datetime.now(UTC))
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//BotballDashboard//Deadlines//DE",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_ics_escape(calendar_name)}",
    ]
    for entry in entries:
        start, end = entry["start"], entry["end"]
        lines += ["BEGIN:VEVENT", f"UID:{entry['id']}@botball-dashboard", f"DTSTAMP:{stamp}"]
        if isinstance(start, datetime):
            lines.append(f"DTSTART:{_ics_datetime(start)}")
            if isinstance(end, datetime):
                lines.append(f"DTEND:{_ics_datetime(end)}")
        else:
            # All-day: DTEND is exclusive, so a single day ends the next day.
            last = end if isinstance(end, date) and not isinstance(end, datetime) else start
            lines.append(f"DTSTART;VALUE=DATE:{start.strftime('%Y%m%d')}")
            lines.append(f"DTEND;VALUE=DATE:{(last + timedelta(days=1)).strftime('%Y%m%d')}")
        summary = entry["title"]
        if entry.get("season_name"):
            summary = f"{summary} ({entry['season_name']})"
        lines.append(f"SUMMARY:{_ics_escape(summary)}")
        if entry.get("description"):
            lines.append(f"DESCRIPTION:{_ics_escape(str(entry['description']))}")
        lines.append(f"CATEGORIES:{_ics_escape(entry['kind'])}")
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"


# ── Feed tokens ───────────────────────────────────────────────────────────────


def hash_feed_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def get_feed_token(db: AsyncSession, user_id: str) -> CalendarFeedToken | None:
    result = await db.execute(select(CalendarFeedToken).where(CalendarFeedToken.user_id == user_id))
    return result.scalar_one_or_none()


async def rotate_feed_token(db: AsyncSession, user_id: str) -> str:
    """Issue a new feed token; any earlier URL of this user stops working."""
    token = secrets.token_urlsafe(32)
    existing = await get_feed_token(db, user_id)
    if existing:
        existing.token_hash = hash_feed_token(token)
        existing.created_at = datetime.now(UTC)
        existing.last_used_at = None
    else:
        db.add(CalendarFeedToken(user_id=user_id, token_hash=hash_feed_token(token)))
    await db.flush()
    return token


async def revoke_feed_token(db: AsyncSession, user_id: str) -> None:
    existing = await get_feed_token(db, user_id)
    if existing:
        await db.delete(existing)
        await db.flush()


async def user_for_feed_token(db: AsyncSession, token: str):
    """The active user a feed token belongs to, or None."""
    from sqlalchemy.orm import selectinload

    from modules.auth.models import Role, User

    if not token or len(token) > 200:
        return None
    result = await db.execute(
        select(CalendarFeedToken).where(CalendarFeedToken.token_hash == hash_feed_token(token))
    )
    record = result.scalar_one_or_none()
    if not record:
        return None
    user_result = await db.execute(
        select(User)
        .options(selectinload(User.roles).selectinload(Role.permissions))
        .where(User.id == record.user_id, User.is_active.is_(True))
    )
    user = user_result.scalar_one_or_none()
    if user:
        record.last_used_at = datetime.now(UTC)
    return user
