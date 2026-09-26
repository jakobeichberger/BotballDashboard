"""Official and internal paper deadlines (module 06) and their reminders.

A season can carry any number of PaperDeadline rows. Official deadlines come
from the organizer's call for papers; with ``is_hard_block`` they lock uploads
once passed (organizers can override). Internal deadlines are our own buffer
and only warn. ``Season.paper_submission_deadline`` stays the fallback for
the first submission when no hard official_submission deadline is set.

Reminders go out 7, 3 and 1 day(s) before each deadline, only to whoever
still has to act: teams without a handed-in paper (submission deadlines),
teams asked for a revision (revision deadlines), reviewers with open reviews
(internal_review). They reuse the notification outbox: one row per recipient
group with a dedupe key, so the daily task may run any number of times.
"""

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.domain_events import emit_event
from core.exceptions import NotFoundError, ValidationError
from core.mail_templates import i18n_payload
from modules.paper_review.models import (
    DEADLINE_TYPES,
    OFFICIAL_DEADLINE_TYPES,
    REVIEWABLE_STATUSES,
    Paper,
    PaperDeadline,
    ReviewerAssignment,
)

# Deadlines by which a team has to hand in its paper for the first time.
SUBMISSION_TYPES = frozenset({"official_submission", "internal_draft", "internal_final"})
# Deadlines by which a team asked for a revision has to hand in the new version.
REVISION_TYPES = frozenset({"internal_revision", "official_final"})
# Deadline by which reviewers should have submitted their reviews.
REVIEW_TYPES = frozenset({"internal_review"})
# Dates announced to teams that ask nothing of them.
NOTICE_TYPES = frozenset({"official_notification"})

TYPE_LABELS = {
    "official_submission": "Official paper submission",
    "official_notification": "Notification of acceptance",
    "official_final": "Official final submission",
    "internal_draft": "Internal draft deadline",
    "internal_review": "Internal review deadline",
    "internal_revision": "Internal revision deadline",
    "internal_final": "Internal final submission",
}


# ── CRUD ──────────────────────────────────────────────────────────────────────


async def list_deadlines(db: AsyncSession, season_id: str) -> list[PaperDeadline]:
    result = await db.execute(
        select(PaperDeadline)
        .where(PaperDeadline.season_id == season_id)
        .order_by(PaperDeadline.due_date, PaperDeadline.deadline_type)
    )
    return list(result.scalars().all())


async def get_deadline(db: AsyncSession, deadline_id: str) -> PaperDeadline:
    deadline = await db.get(PaperDeadline, deadline_id)
    if not deadline:
        raise NotFoundError("Paper deadline not found")
    return deadline


def _check_type(deadline_type: str, is_hard_block: bool) -> None:
    if deadline_type not in DEADLINE_TYPES:
        raise ValidationError(f"Unknown deadline type (allowed: {', '.join(DEADLINE_TYPES)})")
    if is_hard_block and deadline_type == "official_notification":
        raise ValidationError("The notification of acceptance does not block uploads")
    if is_hard_block and deadline_type not in OFFICIAL_DEADLINE_TYPES:
        # Internal deadlines only warn (spec: "kein hard Block").
        raise ValidationError("Only official deadlines can block uploads")


async def create_deadline(db: AsyncSession, data: dict) -> PaperDeadline:
    from modules.seasons.lifecycle import ensure_writable
    from modules.seasons.models import Season

    if not await db.get(Season, data["season_id"]):
        raise ValidationError("Season not found")
    await ensure_writable(db, season_id=data["season_id"])
    _check_type(data["deadline_type"], bool(data.get("is_hard_block")))
    deadline = PaperDeadline(**data)
    db.add(deadline)
    await db.flush()
    await db.refresh(deadline)
    return deadline


async def update_deadline(db: AsyncSession, deadline_id: str, changes: dict) -> PaperDeadline:
    from modules.seasons.lifecycle import ensure_writable

    deadline = await get_deadline(db, deadline_id)
    await ensure_writable(db, season_id=deadline.season_id)
    for key in ("deadline_type", "due_date", "is_hard_block"):
        if key in changes and changes[key] is None:
            raise ValidationError(f"{key} must not be empty")
    _check_type(
        changes.get("deadline_type", deadline.deadline_type),
        changes.get("is_hard_block", deadline.is_hard_block),
    )
    for key, value in changes.items():
        setattr(deadline, key, value)
    await db.flush()
    await db.refresh(deadline)
    return deadline


async def delete_deadline(db: AsyncSession, deadline_id: str) -> None:
    from modules.seasons.lifecycle import ensure_writable

    deadline = await get_deadline(db, deadline_id)
    await ensure_writable(db, season_id=deadline.season_id)
    await db.delete(deadline)


# ── Enforcement ───────────────────────────────────────────────────────────────


async def hard_block_date(db: AsyncSession, season_id: str, deadline_type: str) -> date | None:
    """Earliest blocking deadline of ``deadline_type`` in the season."""
    result = await db.execute(
        select(PaperDeadline.due_date)
        .where(
            PaperDeadline.season_id == season_id,
            PaperDeadline.deadline_type == deadline_type,
            PaperDeadline.is_hard_block == True,
        )
        .order_by(PaperDeadline.due_date)
        .limit(1)
    )
    return result.scalar_one_or_none()


# ── Reminders ─────────────────────────────────────────────────────────────────


async def _teams_to_remind(db: AsyncSession, season_id: str, deadline_type: str) -> list[str]:
    """Teams of the season that still have to act before this deadline."""
    from modules.teams.models import TeamSeasonRegistration

    registered = list(
        (
            await db.execute(
                select(TeamSeasonRegistration.team_id).where(
                    TeamSeasonRegistration.season_id == season_id,
                    TeamSeasonRegistration.paper_required == True,
                )
            )
        ).scalars()
    )
    if not registered:
        return []
    papers = {
        team_id: status
        for team_id, status in (
            await db.execute(
                select(Paper.team_id, Paper.status).where(
                    Paper.season_id == season_id, Paper.team_id.in_(registered)
                )
            )
        ).all()
    }
    if deadline_type in REVISION_TYPES:
        return sorted(t for t in registered if papers.get(t) == "revision_requested")
    # Submission deadlines: no paper yet, or only a draft that was never handed in.
    return sorted(t for t in registered if papers.get(t, "draft") == "draft")


async def _reviewers_to_remind(db: AsyncSession, season_id: str) -> list[str]:
    """Reviewers with an open assignment on a paper that is still in review.

    A decided paper (accepted, rejected, sent back for revision) takes no
    more reviews, so its open assignments are no reason for a reminder; an
    archived season is history and reminds nobody.
    """
    from modules.seasons.lifecycle import ARCHIVED
    from modules.seasons.models import Season

    result = await db.execute(
        select(ReviewerAssignment.reviewer_id)
        .join(Paper, Paper.id == ReviewerAssignment.paper_id)
        .join(Season, Season.id == Paper.season_id)
        .where(
            Paper.season_id == season_id,
            ReviewerAssignment.status != "completed",
            Paper.status.in_(REVIEWABLE_STATUSES),
            Season.status != ARCHIVED,
        )
        .distinct()
    )
    return sorted(str(r) for r in result.scalars())


def _due_text(days: int) -> str:
    return "tomorrow" if days == 1 else f"in {days} days"


async def queue_paper_deadline_reminders(db: AsyncSession, today: date | None = None) -> int:
    """Queue reminders for paper deadlines due in 7, 3 and 1 day(s).

    Covers every PaperDeadline and, for seasons without an official_submission
    row, ``Season.paper_submission_deadline``. Returns the number queued.
    """
    from modules.events.notifications import (
        DEADLINE_REMINDER_DAYS,
        team_member_emails,
        team_member_user_ids,
    )
    from modules.seasons.models import Season

    today = today or datetime.now(UTC).date()
    due_dates = {today + timedelta(days=days): days for days in DEADLINE_REMINDER_DAYS}

    # (key, season_id, type, date, label)
    targets: list[tuple[str, str, str, date, str]] = []
    rows = await db.execute(
        select(PaperDeadline).where(PaperDeadline.due_date.in_(list(due_dates)))
    )
    for deadline in rows.scalars():
        targets.append(
            (
                deadline.id,
                deadline.season_id,
                deadline.deadline_type,
                deadline.due_date,
                deadline.label or TYPE_LABELS[deadline.deadline_type],
            )
        )
    seasons = await db.execute(
        select(Season).where(Season.paper_submission_deadline.in_(list(due_dates)))
    )
    for season in seasons.scalars():
        has_official = await db.execute(
            select(PaperDeadline.id).where(
                PaperDeadline.season_id == season.id,
                PaperDeadline.deadline_type == "official_submission",
            )
        )
        if has_official.first() is None and season.paper_submission_deadline:
            targets.append(
                (
                    f"season-{season.id}",
                    season.id,
                    "official_submission",
                    season.paper_submission_deadline,
                    "Paper submission",
                )
            )

    queued = 0
    for key, season_id, deadline_type, due, label in targets:
        # A label typed in for the deadline is kept as is; built-in type
        # names are translated per recipient.
        custom = None if label in (TYPE_LABELS.get(deadline_type), "Paper submission") else label
        days = due_dates[due]
        when = _due_text(days)
        stem = f"paper-deadline:{key}:{due.isoformat()}:{days}"
        if deadline_type in NOTICE_TYPES:
            continue  # the committee's date, nothing for teams to do
        if deadline_type in REVIEW_TYPES:
            for reviewer_id in await _reviewers_to_remind(db, season_id):
                item = await emit_event(
                    db,
                    "paper_deadline_reminder",
                    payload={
                        "title": f"{label} {when}",
                        "message": (f"Your open paper reviews are due {when} ({due.isoformat()})."),
                        **i18n_payload(
                            "paper_deadline_reminder",
                            kind="review",
                            deadline_type=deadline_type,
                            due=due.isoformat(),
                            days=days,
                            label=custom,
                        ),
                        "userId": reviewer_id,
                        "url": "/papers",
                    },
                    dedupe_key=f"{stem}:reviewer:{reviewer_id}",
                )
                queued += item is not None
            continue
        action = (
            "Upload and submit the revised version of your paper"
            if deadline_type in REVISION_TYPES
            else "Your team has not submitted its paper yet"
        )
        for team_id in await _teams_to_remind(db, season_id, deadline_type):
            user_ids = await team_member_user_ids(db, [team_id])
            emails = await team_member_emails(db, [team_id])
            if not user_ids and not emails:
                continue
            item = await emit_event(
                db,
                "paper_deadline_reminder",
                payload={
                    "title": f"{label} {when}",
                    "message": f"{action}. {label}: {due.isoformat()} ({when}).",
                    **i18n_payload(
                        "paper_deadline_reminder",
                        kind="revision" if deadline_type in REVISION_TYPES else "submission",
                        deadline_type=deadline_type,
                        due=due.isoformat(),
                        days=days,
                        label=custom,
                    ),
                    "userIds": user_ids,
                    "emails": emails,
                    "url": "/papers",
                },
                dedupe_key=f"{stem}:team:{team_id}",
            )
            queued += item is not None
    return queued
