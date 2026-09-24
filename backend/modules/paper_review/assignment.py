"""Automatic reviewer assignment.

Fills every open paper of a season (or event) up to N reviewers:

- Pool: active users holding papers:review (optionally narrowed by the
  organizer). Reviewers need no team membership.
- Conflicts: the same rules as a manual assignment – nobody reviews a paper
  of their own team or of another team of the same school.
- Balance: each slot goes to the eligible reviewer with the fewest open
  reviews (counting the ones handed out in this run), then the fewest reviews
  overall; ties are broken by name so a plan is reproducible.
- Papers with the fewest eligible reviewers are served first, so a scarce
  reviewer is not used up by papers that had plenty of alternatives.

With ``dry_run`` only the plan is returned. Otherwise every assignment goes
through service.assign_reviewer (notification, status under_review).
"""

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.exceptions import ValidationError
from modules.paper_review.models import Paper, ReviewerAssignment

# Papers a reviewer can still be added to.
_OPEN_FOR_ASSIGNMENT = ("submitted", "resubmitted", "under_review")


def _school_key(school: str | None) -> str:
    return (school or "").strip().casefold()


async def reviewer_pool(db: AsyncSession, reviewer_ids: list[str] | None = None) -> list:
    """Active users holding papers:review through one of their roles."""
    from modules.auth.models import Permission, Role, User

    query = (
        select(User)
        .join(User.roles)
        .join(Role.permissions)
        .where(User.is_active == True, Permission.name == "papers:review")
        .order_by(User.display_name, User.id)
    )
    pool = list((await db.execute(query)).scalars().unique().all())
    if reviewer_ids is None:
        return pool
    by_id = {user.id: user for user in pool}
    unknown = [rid for rid in reviewer_ids if rid not in by_id]
    if unknown:
        raise ValidationError(
            "Not an active reviewer (papers:review): " + ", ".join(sorted(set(unknown)))
        )
    return [by_id[rid] for rid in dict.fromkeys(reviewer_ids)]


async def _reviewer_schools(db: AsyncSession, user_ids: list[str]) -> dict[str, tuple]:
    """user id -> (team ids, school keys) of the teams the user belongs to."""
    from modules.teams.models import Team, TeamMember

    rows = await db.execute(
        select(TeamMember.user_id, Team.id, Team.school)
        .join(Team, Team.id == TeamMember.team_id)
        .where(TeamMember.user_id.in_(user_ids))
    )
    result: dict[str, tuple[set[str], set[str]]] = {uid: (set(), set()) for uid in user_ids}
    for user_id, team_id, school in rows.all():
        teams, schools = result[user_id]
        teams.add(team_id)
        if _school_key(school):
            schools.add(_school_key(school))
    return result


async def auto_assign(
    db: AsyncSession,
    *,
    season_id: str,
    event_id: str | None,
    reviewers_per_paper: int,
    assigned_by: str,
    reviewer_ids: list[str] | None = None,
    due_at: datetime | None = None,
    dry_run: bool = False,
) -> dict:
    from modules.paper_review.service import assign_reviewer
    from modules.teams.models import Team

    pool = await reviewer_pool(db, reviewer_ids)
    query = select(Paper).where(
        Paper.season_id == season_id,
        Paper.status.in_(_OPEN_FOR_ASSIGNMENT),
        Paper.finalized_at.is_(None),
    )
    if event_id:
        query = query.where(Paper.event_id == event_id)
    papers = list((await db.execute(query.order_by(Paper.created_at))).scalars().all())

    assignments = list(
        (
            await db.execute(
                select(
                    ReviewerAssignment.reviewer_id,
                    ReviewerAssignment.paper_id,
                    ReviewerAssignment.status,
                )
            )
        ).all()
    )
    open_load = {user.id: 0 for user in pool}
    total_load = {user.id: 0 for user in pool}
    assigned_to: dict[str, set[str]] = {paper.id: set() for paper in papers}
    for reviewer_id, paper_id, status in assignments:
        if reviewer_id in open_load:
            total_load[reviewer_id] += 1
            if status != "completed":
                open_load[reviewer_id] += 1
        if paper_id in assigned_to:
            assigned_to[paper_id].add(reviewer_id)

    schools_of = await _reviewer_schools(db, [user.id for user in pool])
    team_school = {
        team_id: _school_key(school)
        for team_id, school in (
            await db.execute(
                select(Team.id, Team.school).where(Team.id.in_({p.team_id for p in papers}))
            )
        ).all()
    }

    def eligible(paper: Paper) -> list:
        school = team_school.get(paper.team_id, "")
        candidates = []
        for user in pool:
            teams, schools = schools_of[user.id]
            if user.id in assigned_to[paper.id] or paper.team_id in teams:
                continue
            if school and school in schools:
                continue
            candidates.append(user)
        return candidates

    plan: list[tuple[Paper, Any]] = []
    unfilled = []
    needing = [p for p in papers if len(assigned_to[p.id]) < reviewers_per_paper]
    needing.sort(key=lambda p: (len(eligible(p)), p.created_at))
    for paper in needing:
        missing = reviewers_per_paper - len(assigned_to[paper.id])
        candidates = eligible(paper)
        for _ in range(missing):
            if not candidates:
                break
            best = min(
                candidates,
                key=lambda u: (open_load[u.id], total_load[u.id], u.display_name, u.id),
            )
            candidates.remove(best)
            open_load[best.id] += 1
            total_load[best.id] += 1
            assigned_to[paper.id].add(best.id)
            plan.append((paper, best))
            missing -= 1
        if missing:
            unfilled.append({"paper_id": paper.id, "paper_title": paper.title, "missing": missing})

    if not dry_run:
        for paper, reviewer in plan:
            await assign_reviewer(db, paper.id, reviewer.id, assigned_by, due_at)

    return {
        "dry_run": dry_run,
        "assignments": [
            {
                "paper_id": paper.id,
                "paper_title": paper.title,
                "reviewer_id": reviewer.id,
                "reviewer_name": reviewer.display_name,
            }
            for paper, reviewer in plan
        ],
        "unfilled": unfilled,
    }
