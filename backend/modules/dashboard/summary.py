"""Role-aware dashboard summary (GET /dashboard/summary).

One call returns the sections the current user may see:

- ``juror``  (scoring:admin): scores awaiting confirmation, next scheduled
  matches, OCR scans still waiting for review;
- ``mentor`` (member of a team): per own team the next matches, paper status,
  print jobs and latest scores;
- ``admin``  (organizers): "X of N" progress figures for the event;
- ``deadlines``: the next upcoming deadlines, for everyone.

A section the user may not see is ``null`` rather than empty, so the frontend
can tell "nothing to do" from "not for you".
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.auth import has_elevated_access, own_team_ids
from modules.auth.models import User
from modules.dashboard import calendar
from modules.dashboard.analytics import _get_event, _team_names, seeding_table
from modules.events.models import EventPhase, EventRegistration, MatchParticipant, ScheduledMatch
from modules.events.module_access import event_modules
from modules.paper_review.models import Paper, ReviewerAssignment
from modules.printing.models import PrintJob
from modules.scoring.competition_models import DEResult, DocumentationScore
from modules.scoring.models import Match
from modules.scoring.score_sheets.models import ScoreSheetScan
from modules.teams.models import TeamMember

OPEN_SCAN_STATUSES = ("queued", "processing", "review")
OPEN_PRINT_STATUSES = ("pending", "approved", "queued", "printing")
ADMIN_PERMISSIONS = ("dashboard:write", "events:write", "teams:admin")
UPCOMING_MATCH_STATUSES = ("scheduled", "called", "running")


async def build_summary(db: AsyncSession, user, event_id: str) -> dict[str, Any]:
    event = await _get_event(db, event_id)
    # Looked up once and handed to every section that needs it.
    team_ids = await own_team_ids(db, user)

    season_ids = await calendar.relevant_season_ids(db, user, team_ids=team_ids)
    season_ids.add(event.season_id)
    deadlines = calendar.upcoming(
        await calendar.collect_deadlines(db, user, season_ids, team_ids=team_ids), 5
    )

    return {
        "event_id": event.id,
        # Effective feature modules, so the views can leave out paper/printing
        # figures of events that do not use them.
        "modules": await event_modules(db, event),
        "juror": await _juror_section(db, event.id)
        if await has_elevated_access(db, user, "scoring:admin")
        else None,
        "mentor": await _mentor_section(db, event, team_ids) if team_ids else None,
        "admin": await _admin_section(db, event)
        if await has_elevated_access(db, user, ADMIN_PERMISSIONS)
        else None,
        "deadlines": deadlines,
    }


def _upcoming_query(event_id: str):
    return (
        select(ScheduledMatch)
        .options(selectinload(ScheduledMatch.participants).selectinload(MatchParticipant.team))
        .where(
            ScheduledMatch.event_id == event_id,
            ScheduledMatch.status.in_(UPCOMING_MATCH_STATUSES),
        )
        .order_by(
            ScheduledMatch.scheduled_at.is_(None),
            ScheduledMatch.scheduled_at,
            ScheduledMatch.round_number,
            ScheduledMatch.sequence_number,
        )
    )


async def _serialize_matches(
    db: AsyncSession, matches: list[ScheduledMatch]
) -> dict[str, dict[str, Any]]:
    """Scheduled matches as summary rows keyed by id (one phase lookup for all)."""
    phase_names: dict[str, str] = {}
    if matches:
        phases = await db.execute(
            select(EventPhase.id, EventPhase.name).where(
                EventPhase.id.in_({m.phase_id for m in matches})
            )
        )
        phase_names = {r.id: r.name for r in phases}
    return {
        m.id: {
            "id": m.id,
            "code": m.code,
            "round_number": m.round_number,
            "table_number": m.table_number,
            "scheduled_at": m.scheduled_at,
            "status": m.status,
            "phase_name": phase_names.get(m.phase_id),
            "teams": [
                {"team_id": p.team_id, "team_name": p.team_name}
                for p in sorted(m.participants, key=lambda p: p.position)
            ],
        }
        for m in matches
    }


async def _upcoming_matches(
    db: AsyncSession, event_id: str, limit: int = 5
) -> list[dict[str, Any]]:
    """Next scheduled matches of the event."""
    matches = list((await db.execute(_upcoming_query(event_id).limit(limit))).scalars().all())
    rows = await _serialize_matches(db, matches)
    return [rows[m.id] for m in matches]


async def _upcoming_by_team(
    db: AsyncSession, event_id: str, team_ids: set[str], limit: int
) -> dict[str, list[dict[str, Any]]]:
    """The next `limit` scheduled matches of each of `team_ids`, in two queries."""
    query = _upcoming_query(event_id).where(
        ScheduledMatch.id.in_(
            select(MatchParticipant.scheduled_match_id).where(
                MatchParticipant.team_id.in_(team_ids)
            )
        )
    )
    matches = list((await db.execute(query)).scalars().all())
    per_team: dict[str, list[ScheduledMatch]] = {tid: [] for tid in team_ids}
    for match in matches:
        for tid in {p.team_id for p in match.participants} & team_ids:
            if len(per_team[tid]) < limit:
                per_team[tid].append(match)
    used = {m.id: m for team_matches in per_team.values() for m in team_matches}
    rows = await _serialize_matches(db, list(used.values()))
    return {tid: [rows[m.id] for m in team_matches] for tid, team_matches in per_team.items()}


async def _juror_section(db: AsyncSession, event_id: str) -> dict[str, Any]:
    unconfirmed_q = select(Match).where(
        Match.event_id == event_id,
        Match.confirmed_at.is_(None),
        Match.is_practice.is_(False),
    )
    unconfirmed = list(
        (await db.execute(unconfirmed_q.order_by(Match.created_at.desc()).limit(20)))
        .scalars()
        .all()
    )
    unconfirmed_count = (
        await db.execute(select(func.count()).select_from(unconfirmed_q.subquery()))
    ).scalar() or 0

    # A score entered by a member of the scored team (mentor self-service)
    # deserves a closer look than one typed in by a juror.
    member_pairs: set[tuple[str, str]] = set()
    entered_by = {m.entered_by for m in unconfirmed if m.entered_by}
    if entered_by:
        rows = await db.execute(
            select(TeamMember.team_id, TeamMember.user_id).where(TeamMember.user_id.in_(entered_by))
        )
        member_pairs = {(r.team_id, r.user_id) for r in rows}
    users: dict[str, str] = {}
    if entered_by:
        rows = await db.execute(select(User.id, User.display_name).where(User.id.in_(entered_by)))
        users = {r.id: r.display_name for r in rows}
    names = await _team_names(db, {m.team_id for m in unconfirmed})

    scans_q = select(ScoreSheetScan).where(
        ScoreSheetScan.event_id == event_id, ScoreSheetScan.status.in_(OPEN_SCAN_STATUSES)
    )
    scans = list(
        (await db.execute(scans_q.order_by(ScoreSheetScan.created_at).limit(10))).scalars().all()
    )
    scans_count = (
        await db.execute(select(func.count()).select_from(scans_q.subquery()))
    ).scalar() or 0
    scan_names = await _team_names(db, {s.team_id for s in scans})

    unconfirmed_rows = [
        {
            "match_id": m.id,
            "team_id": m.team_id,
            "team_name": names.get(m.team_id, {}).get("name", m.team_id),
            "round_number": m.round_number,
            "total_score": m.total_score,
            "is_disqualified": m.is_disqualified,
            "created_at": m.created_at,
            "entered_by_name": users.get(m.entered_by or ""),
            "entered_by_team_member": (m.team_id, m.entered_by) in member_pairs,
        }
        for m in unconfirmed
    ]
    # Mentor submissions first: they are the ones that need a second pair of eyes.
    unconfirmed_rows.sort(key=lambda r: not r["entered_by_team_member"])
    return {
        "unconfirmed_count": unconfirmed_count,
        "unconfirmed": unconfirmed_rows,
        "upcoming_matches": await _upcoming_matches(db, event_id),
        "open_scans_count": scans_count,
        "open_scans": [
            {
                "id": s.id,
                "team_id": s.team_id,
                "team_name": scan_names.get(s.team_id, {}).get("name", s.team_id),
                "status": s.status,
                "file_name": s.file_name,
                "created_at": s.created_at,
            }
            for s in scans
        ],
    }


async def _mentor_section(db: AsyncSession, event, team_ids: set[str]) -> dict[str, Any]:
    """Per own team: seeding, next matches, paper, print jobs and latest scores.

    Each kind of data is loaded for all of the mentor's teams at once and
    grouped here, instead of four queries per team.
    """
    names = await _team_names(db, team_ids)
    seeding = {r["team_id"]: r for r in await seeding_table(db, event)}
    next_matches = await _upcoming_by_team(db, event.id, team_ids, limit=3)

    papers: dict[str, Paper] = {}
    paper_rows = await db.execute(
        select(Paper)
        .where(Paper.team_id.in_(team_ids), Paper.season_id == event.season_id)
        .order_by(Paper.updated_at.desc())
    )
    for paper_row in paper_rows.scalars():
        papers.setdefault(paper_row.team_id, paper_row)  # the most recently updated

    jobs_by_team: dict[str, list[PrintJob]] = defaultdict(list)
    job_rows = await db.execute(
        select(PrintJob)
        .where(PrintJob.team_id.in_(team_ids), PrintJob.season_id == event.season_id)
        .order_by(PrintJob.created_at.desc())
    )
    for job in job_rows.scalars():
        jobs_by_team[job.team_id].append(job)

    latest_by_team: dict[str, list[Match]] = defaultdict(list)
    match_rows = await db.execute(
        select(Match)
        .where(Match.team_id.in_(team_ids), Match.event_id == event.id)
        .order_by(Match.created_at.desc())
    )
    for match in match_rows.scalars():
        if len(latest_by_team[match.team_id]) < 5:
            latest_by_team[match.team_id].append(match)

    teams = []
    for tid in sorted(team_ids, key=lambda t: names.get(t, {}).get("name", t)):
        paper = papers.get(tid)
        jobs = jobs_by_team.get(tid, [])
        latest = latest_by_team.get(tid, [])
        seed = seeding.get(tid)
        teams.append(
            {
                "team_id": tid,
                "team_name": names.get(tid, {}).get("name", tid),
                "seeding_rank": seed["rank"] if seed else None,
                "seed_score": seed["seed_score"] if seed else None,
                "seeding_teams": len(seeding),
                "next_matches": next_matches.get(tid, []),
                "paper": {
                    "id": paper.id,
                    "title": paper.title,
                    "status": paper.status,
                    "submitted_at": paper.submitted_at,
                    "final_score": paper.final_score,
                }
                if paper
                else None,
                "print_jobs": {
                    "open": sum(1 for j in jobs if j.status in OPEN_PRINT_STATUSES),
                    "completed": sum(1 for j in jobs if j.status == "completed"),
                    "recent": [
                        {
                            "id": j.id,
                            "file_name": j.file_name,
                            "status": j.status,
                            "created_at": j.created_at,
                        }
                        for j in jobs[:3]
                    ],
                },
                "latest_scores": [
                    {
                        "match_id": m.id,
                        "round_number": m.round_number,
                        "total_score": m.total_score,
                        "is_practice": m.is_practice,
                        "is_disqualified": m.is_disqualified,
                        "confirmed": m.confirmed_at is not None,
                        "created_at": m.created_at,
                    }
                    for m in latest
                ],
            }
        )
    return {"teams": teams}


async def _count(db: AsyncSession, query) -> int:
    return (await db.execute(select(func.count()).select_from(query.subquery()))).scalar() or 0


async def _admin_section(db: AsyncSession, event) -> dict[str, Any]:
    registered_ids = set(
        (
            await db.execute(
                select(EventRegistration.team_id).where(EventRegistration.event_id == event.id)
            )
        )
        .scalars()
        .all()
    )
    checked_in = await _count(
        db,
        select(EventRegistration.id).where(
            EventRegistration.event_id == event.id, EventRegistration.checked_in_at.isnot(None)
        ),
    )
    scored_ids = set(
        (
            await db.execute(
                select(Match.team_id)
                .where(Match.event_id == event.id, Match.is_practice.is_(False))
                .distinct()
            )
        )
        .scalars()
        .all()
    )
    # Papers belong to the season; "submitted" means anything past a draft.
    paper_rows = (
        await db.execute(
            select(Paper.team_id, Paper.status).where(Paper.season_id == event.season_id)
        )
    ).all()
    paper_teams = {
        r.team_id
        for r in paper_rows
        if r.status != "draft" and (not registered_ids or r.team_id in registered_ids)
    }
    reviews_pending = await _count(
        db,
        select(ReviewerAssignment.id)
        .join(Paper, Paper.id == ReviewerAssignment.paper_id)
        .where(Paper.season_id == event.season_id, ReviewerAssignment.status != "completed"),
    )
    runs = (
        await db.execute(
            select(Match.is_practice, Match.confirmed_at).where(Match.event_id == event.id)
        )
    ).all()
    print_rows = (
        await db.execute(
            select(PrintJob.status).where(
                (PrintJob.event_id == event.id)
                | ((PrintJob.event_id.is_(None)) & (PrintJob.season_id == event.season_id))
            )
        )
    ).all()
    de_results = await _count(db, select(DEResult.id).where(DEResult.event_id == event.id))
    doc_scores = await _count(
        db, select(DocumentationScore.id).where(DocumentationScore.event_id == event.id)
    )
    statuses = [r.status for r in print_rows]
    return {
        "teams_registered": len(registered_ids),
        "teams_checked_in": checked_in,
        "teams_scored": len(scored_ids & registered_ids) if registered_ids else len(scored_ids),
        "teams_with_paper": len(paper_teams),
        "papers_total": len(paper_rows),
        "reviews_pending": reviews_pending,
        "official_runs": sum(1 for r in runs if not r.is_practice),
        "practice_runs": sum(1 for r in runs if r.is_practice),
        "unconfirmed_runs": sum(1 for r in runs if not r.is_practice and r.confirmed_at is None),
        "de_results": de_results,
        "doc_scores": doc_scores,
        "print_queue": {
            "pending": statuses.count("pending"),
            "active": sum(1 for s in statuses if s in ("approved", "queued", "printing")),
            "completed": statuses.count("completed"),
            "failed": statuses.count("failed"),
        },
        "generated_at": datetime.now(UTC),
    }
