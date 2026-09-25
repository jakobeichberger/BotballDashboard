"""Awards of an event: templates, computed placings, nominations, jury decisions.

Computed awards take their places from the event's rankings — the same
formula rows as the overall ranking (``formula_service``), so an award can
never disagree with the published scores:

* overall / doc / adapted_doc / aerial / jbc / paper: the formula value
  (overall, doc_score, adapted_doc_score, aerial_score, jbc_points, paper),
  highest first; a team without a value (0) takes no place.
* seeding: the displayed seeding rank (``seed_rank``).
* de: the DE rank; with ``per_course`` within each DE bracket, otherwise on
  the weighted DE score across brackets.

Places are competition ranks (ties share a place); an award lists every team
whose place is within ``places``. Red-carded teams are out of every ranking
and so of every computed award. Judged awards are placed by the jury from the
nominations; ``paper_on_stage`` seeds the nominations of Best Paper
Presentation with the papers presented on stage.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.exceptions import ConflictError, NotFoundError, ValidationError
from modules.awards.models import AwardCategory, AwardNomination, AwardResult, EventAwards
from modules.awards.templates import TEMPLATES
from modules.events.models import Event, EventRegistration
from modules.scoring.ranking import rank_descending
from modules.seasons.categories import kind_of
from modules.seasons.lifecycle import ensure_writable
from modules.teams.models import Team

#: Formula column each value-ranked source reads.
VALUE_COLUMNS = {
    "overall": "overall",
    "doc": "doc_score",
    "adapted_doc": "adapted_doc_score",
    "aerial": "aerial_score",
    "jbc": "jbc_points",
    "paper": "paper",
}
#: Category kinds a source covers when an award names no category.
SOURCE_KINDS = {"paper": ("botball", "open"), "doc": ("botball",), "adapted_doc": ("botball",)}


# ── Loading ───────────────────────────────────────────────────────────────────


async def _event(db: AsyncSession, event_id: str) -> Event:
    event = await db.get(Event, event_id)
    if event is None:
        raise NotFoundError("Event not found")
    return event


async def _settings(db: AsyncSession, event_id: str) -> EventAwards:
    row = await db.get(EventAwards, event_id)
    if row is None:
        row = EventAwards(event_id=event_id, published=False)
        db.add(row)
        await db.flush()
    return row


async def get_award(db: AsyncSession, award_id: str) -> AwardCategory:
    award = await db.get(AwardCategory, award_id)
    if award is None:
        raise NotFoundError("Award not found")
    return award


async def _teams(db: AsyncSession, team_ids: set[str]) -> dict[str, Team]:
    if not team_ids:
        return {}
    rows = await db.execute(select(Team).where(Team.id.in_(team_ids)))
    return {team.id: team for team in rows.scalars()}


async def event_awards(db: AsyncSession, event_id: str) -> dict[str, Any]:
    """Every award of the event with its nominations and results."""
    await _event(db, event_id)
    settings = await db.get(EventAwards, event_id)
    awards = list(
        (
            await db.execute(
                select(AwardCategory)
                .where(AwardCategory.event_id == event_id)
                .order_by(AwardCategory.sort_order, AwardCategory.label)
            )
        ).scalars()
    )
    ids = [a.id for a in awards]
    nominations: dict[str, list[AwardNomination]] = defaultdict(list)
    results: dict[str, list[AwardResult]] = defaultdict(list)
    if ids:
        for nomination in (
            await db.execute(
                select(AwardNomination)
                .where(AwardNomination.award_id.in_(ids))
                .order_by(AwardNomination.created_at)
            )
        ).scalars():
            nominations[nomination.award_id].append(nomination)
        for result in (
            await db.execute(
                select(AwardResult)
                .where(AwardResult.award_id.in_(ids))
                .order_by(AwardResult.course, AwardResult.place)
            )
        ).scalars():
            results[result.award_id].append(result)
    team_ids = {n.team_id for rows in nominations.values() for n in rows}
    team_ids |= {r.team_id for rows in results.values() for r in rows}
    teams = await _teams(db, team_ids)

    def team_name(team_id: str) -> str | None:
        team = teams.get(team_id)
        return team.name if team else None

    return {
        "event_id": event_id,
        "template": settings.template if settings else None,
        "published": bool(settings and settings.published),
        "published_at": settings.published_at if settings else None,
        "awards": [
            {
                **{
                    field: getattr(award, field)
                    for field in (
                        "id",
                        "event_id",
                        "key",
                        "label",
                        "description",
                        "kind",
                        "source",
                        "team_category",
                        "places",
                        "per_course",
                        "sort_order",
                    )
                },
                "nominations": [
                    {
                        "id": n.id,
                        "team_id": n.team_id,
                        "team_name": team_name(n.team_id),
                        "note": n.note,
                        "nominated_by": n.nominated_by,
                        "created_at": n.created_at,
                    }
                    for n in nominations[award.id]
                ],
                "results": [
                    {
                        "team_id": r.team_id,
                        "team_name": team_name(r.team_id),
                        "team_number": teams[r.team_id].team_number if r.team_id in teams else None,
                        "place": r.place,
                        "course": r.course,
                        "score": r.score,
                        "note": r.note,
                    }
                    for r in results[award.id]
                ],
            }
            for award in awards
        ],
    }


# ── Templates and categories ──────────────────────────────────────────────────


def list_templates() -> list[dict[str, Any]]:
    return [{"id": key, **value} for key, value in TEMPLATES.items()]


async def apply_template(db: AsyncSession, event_id: str, template_id: str) -> dict[str, Any]:
    """Add the template's awards the event does not have yet (by key)."""
    template = TEMPLATES.get(template_id)
    if template is None:
        raise NotFoundError(f"Unknown award template '{template_id}'")
    await _event(db, event_id)
    await ensure_writable(db, event_id=event_id)
    existing = set(
        (
            await db.execute(select(AwardCategory.key).where(AwardCategory.event_id == event_id))
        ).scalars()
    )
    offset = len(existing)
    for index, spec in enumerate(template["awards"]):
        if spec["key"] in existing:
            continue
        db.add(AwardCategory(event_id=event_id, sort_order=(offset + index) * 10, **spec))
    settings = await _settings(db, event_id)
    settings.template = template_id
    await db.flush()
    return await event_awards(db, event_id)


async def create_award(db: AsyncSession, event_id: str, data: dict[str, Any]) -> AwardCategory:
    await _event(db, event_id)
    await ensure_writable(db, event_id=event_id)
    duplicate = await db.execute(
        select(AwardCategory.id).where(
            AwardCategory.event_id == event_id, AwardCategory.key == data["key"]
        )
    )
    if duplicate.first() is not None:
        raise ConflictError(f"The event already has an award '{data['key']}'")
    if data.get("sort_order") is None:
        data["sort_order"] = 1000
    award = AwardCategory(event_id=event_id, **data)
    db.add(award)
    await db.flush()
    return award


async def update_award(db: AsyncSession, award_id: str, data: dict[str, Any]) -> AwardCategory:
    award = await get_award(db, award_id)
    await ensure_writable(db, event_id=award.event_id)
    for key, value in data.items():
        if key == "sort_order" and value is None:
            continue
        setattr(award, key, value)
    await db.flush()
    return award


async def delete_award(db: AsyncSession, award_id: str) -> None:
    award = await get_award(db, award_id)
    await ensure_writable(db, event_id=award.event_id)
    await db.delete(award)
    await db.flush()


# ── Nominations and decisions ─────────────────────────────────────────────────


async def _assert_team(db: AsyncSession, team_id: str) -> None:
    if await db.get(Team, team_id) is None:
        raise NotFoundError("Team not found")


async def nominate(
    db: AsyncSession, award_id: str, team_id: str, note: str | None, user_id: str | None
) -> AwardNomination:
    award = await get_award(db, award_id)
    await ensure_writable(db, event_id=award.event_id)
    await _assert_team(db, team_id)
    existing = (
        await db.execute(
            select(AwardNomination).where(
                AwardNomination.award_id == award_id, AwardNomination.team_id == team_id
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        existing.note = note or existing.note
        await db.flush()
        return existing
    nomination = AwardNomination(
        award_id=award_id, team_id=team_id, note=note, nominated_by=user_id
    )
    db.add(nomination)
    await db.flush()
    return nomination


async def withdraw_nomination(db: AsyncSession, award_id: str, team_id: str) -> None:
    award = await get_award(db, award_id)
    await ensure_writable(db, event_id=award.event_id)
    await db.execute(
        delete(AwardNomination).where(
            AwardNomination.award_id == award_id, AwardNomination.team_id == team_id
        )
    )


async def decide(
    db: AsyncSession, award_id: str, placements: list[dict[str, Any]], user_id: str | None
) -> None:
    """The jury's placing (replaces the award's results).

    Places may be shared; a place beyond the award's number of places is
    refused. For a computed award this overrides the computed placing until
    the next "compute".
    """
    award = await get_award(db, award_id)
    await ensure_writable(db, event_id=award.event_id)
    teams = [p["team_id"] for p in placements]
    if len(teams) != len(set(teams)):
        raise ValidationError("A team can take only one place per award")
    for placement in placements:
        if placement["place"] > award.places:
            raise ValidationError(f"{award.label} has {award.places} place(s)")
        await _assert_team(db, placement["team_id"])
    await _replace_results(db, award, placements, user_id)


async def _replace_results(
    db: AsyncSession, award: AwardCategory, placements: list[dict[str, Any]], user_id: str | None
) -> None:
    await db.execute(delete(AwardResult).where(AwardResult.award_id == award.id))
    now = datetime.now(UTC)
    for placement in placements:
        db.add(
            AwardResult(
                award_id=award.id,
                team_id=placement["team_id"],
                place=placement["place"],
                course=placement.get("course"),
                score=placement.get("score"),
                note=placement.get("note"),
                decided_by=user_id,
                decided_at=now,
            )
        )
    await db.flush()


# ── Computing placings ────────────────────────────────────────────────────────


def _positive(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value) if value > 0 else None


def placings(
    rows: list[dict[str, Any]], source: str, places: int, per_course: bool
) -> list[dict[str, Any]]:
    """Places of one award from formula rows (pure; see the module docstring)."""
    eligible = [r for r in rows if r.get("rank") is not None and not r.get("disqualified")]
    groups: dict[str | None, list[dict[str, Any]]] = defaultdict(list)
    for row in eligible:
        course = (row.get("de_bracket") or None) if per_course else None
        if per_course and course is None:
            continue
        groups[course].append(row)

    out: list[dict[str, Any]] = []
    for course, members in groups.items():
        if source == "seeding":
            # Only teams that scored in seeding: without runs every team
            # shares the last seeding rank.
            scored = [
                (r, -float(r["seed_rank"]), r.get("seed_total"))
                for r in members
                if r.get("seed_rank") and any(v > 0 for v in r.get("seed_runs") or [])
            ]
        elif source == "de" and per_course:
            scored = [
                (r, -float(r["de_rank"]), r.get("de_score")) for r in members if r.get("de_rank")
            ]
        elif source == "de":
            scored = [
                (r, float(r.get("de_score") or 0.0), r.get("de_score"))
                for r in members
                if r.get("de_rank")
            ]
        else:
            column = VALUE_COLUMNS[source]
            scored = [
                (r, value, value)
                for r in members
                if (value := _positive(r.get(column))) is not None
            ]
        for place, (row, _, score) in rank_descending(scored, lambda item: item[1]):
            if place > places:
                break
            out.append(
                {
                    "team_id": row["team_id"],
                    "place": place,
                    "course": course,
                    "score": float(score) if isinstance(score, int | float) else None,
                }
            )
    return out


async def _source_rows(
    db: AsyncSession, event_id: str, award: AwardCategory, data: Any
) -> list[dict[str, Any]]:
    from modules.scoring import formula_service

    if award.team_category:
        categories = [award.team_category]
    else:
        kinds = SOURCE_KINDS.get(award.source or "")
        known = list(data.categories) + sorted(
            {c for c in data.participants.values() if c not in data.categories}
        )
        categories = [c for c in known if kinds is None or kind_of(data.categories, c) in kinds]
    rows: list[dict[str, Any]] = []
    for category in categories:
        ranked, _ = await formula_service.compute_category_ranking(
            db, event_id, category, data=data
        )
        rows.extend(ranked)
    return rows


async def _seed_stage_nominations(
    db: AsyncSession, event: Event, award: AwardCategory, user_id: str | None
) -> None:
    from modules.paper_review.models import Paper

    registered = select(EventRegistration.team_id).where(EventRegistration.event_id == event.id)
    team_ids = (
        await db.execute(
            select(Paper.team_id).where(
                Paper.season_id == event.season_id,
                Paper.presented_on_stage.is_(True),
                Paper.team_id.in_(registered),
            )
        )
    ).scalars()
    for team_id in team_ids:
        await nominate(db, award.id, team_id, None, user_id)


async def compute(
    db: AsyncSession, event_id: str, user_id: str | None, award_id: str | None = None
) -> dict[str, Any]:
    """Fill every computed award (or one) from the current rankings."""
    from modules.scoring import formula_service

    event = await _event(db, event_id)
    await ensure_writable(db, event_id=event_id)
    query = select(AwardCategory).where(AwardCategory.event_id == event_id)
    if award_id:
        query = query.where(AwardCategory.id == award_id)
    awards = list((await db.execute(query)).scalars())
    data = await formula_service.load_event_inputs(db, event_id)
    for award in awards:
        if award.kind == "judged":
            if award.source == "paper_on_stage":
                await _seed_stage_nominations(db, event, award, user_id)
            continue
        if not award.source:
            continue
        rows = await _source_rows(db, event_id, award, data)
        await _replace_results(
            db, award, placings(rows, award.source, award.places, award.per_course), user_id
        )
    return await event_awards(db, event_id)


# ── Publishing ────────────────────────────────────────────────────────────────


async def set_published(db: AsyncSession, event_id: str, published: bool) -> dict[str, Any]:
    await _event(db, event_id)
    await ensure_writable(db, event_id=event_id)
    settings = await _settings(db, event_id)
    settings.published = published
    settings.published_at = datetime.now(UTC) if published else None
    await db.flush()
    return await event_awards(db, event_id)


async def public_awards(db: AsyncSession, event: Event) -> list[dict[str, Any]]:
    """Published awards with their placed teams only (no nominations, no notes)."""
    settings = await db.get(EventAwards, event.id)
    if settings is None or not settings.published:
        raise NotFoundError("Awards are not published")
    data = await event_awards(db, event.id)
    return [
        {
            "key": award["key"],
            "label": award["label"],
            "results": [{**r, "note": None} for r in award["results"]],
        }
        for award in data["awards"]
        if award["results"]
    ]


def export_rows(data: dict[str, Any]) -> list[list[Any]]:
    """Award, course, place, team number, team, score — one row per placed team."""
    rows: list[list[Any]] = []
    for award in data["awards"]:
        for result in award["results"]:
            rows.append(
                [
                    award["label"],
                    result["course"] or "",
                    result["place"],
                    result["team_number"] or "",
                    result["team_name"] or result["team_id"],
                    "" if result["score"] is None else round(result["score"], 4),
                ]
            )
    return rows
