from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.exceptions import ConflictError, NotFoundError, ValidationError
from modules.events.models import (
    Event,
    EventPhase,
    EventRegistration,
    MatchParticipant,
    ScheduledMatch,
)
from modules.seasons.models import CompetitionLevel, Season
from modules.teams.models import Team


async def list_events(
    db: AsyncSession, season_id: str | None = None, status: str | None = None
) -> list[Event]:
    query = select(Event).order_by(Event.starts_at.desc().nullslast(), Event.name)
    if season_id:
        query = query.where(Event.season_id == season_id)
    if status:
        query = query.where(Event.status == status)
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_event(db: AsyncSession, event_id: str) -> Event:
    result = await db.execute(select(Event).where(Event.id == event_id))
    event = result.scalar_one_or_none()
    if not event:
        raise NotFoundError("Event not found")
    return event


async def get_public_event(db: AsyncSession, slug: str) -> Event:
    result = await db.execute(
        select(Event).where(
            Event.slug == slug,
            Event.status.in_(("published", "live", "completed")),
        )
    )
    event = result.scalar_one_or_none()
    if not event:
        raise NotFoundError("Public event not found")
    return event


async def create_event(db: AsyncSession, data: dict) -> Event:
    if not await db.get(Season, data["season_id"]):
        raise NotFoundError("Season not found")
    event = Event(**data)
    db.add(event)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise ConflictError("Event slug already exists") from exc
    await db.refresh(event)
    return event


async def update_event(db: AsyncSession, event_id: str, data: dict) -> Event:
    event = await get_event(db, event_id)
    for key, value in data.items():
        setattr(event, key, value)
    if event.starts_at and event.ends_at and event.ends_at <= event.starts_at:
        raise ValidationError("ends_at must be after starts_at")
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise ConflictError("Event slug already exists") from exc
    await db.refresh(event)
    return event


async def delete_event(db: AsyncSession, event_id: str) -> None:
    event = await get_event(db, event_id)
    if event.status in ("live", "completed"):
        raise ConflictError("Live or completed events cannot be deleted")
    await db.delete(event)


async def list_registrations(db: AsyncSession, event_id: str) -> list[EventRegistration]:
    await get_event(db, event_id)
    result = await db.execute(
        select(EventRegistration)
        .where(EventRegistration.event_id == event_id)
        .order_by(EventRegistration.seed_number.nullslast(), EventRegistration.registered_at)
    )
    return list(result.scalars().all())


async def add_registration(db: AsyncSession, event_id: str, data: dict) -> EventRegistration:
    event = await get_event(db, event_id)
    team = await db.get(Team, data["team_id"])
    if not team:
        raise NotFoundError("Team not found")
    level_id = data.get("competition_level_id")
    if level_id and not await db.get(CompetitionLevel, level_id):
        raise NotFoundError("Competition level not found")

    registration = EventRegistration(event_id=event.id, **data)
    db.add(registration)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise ConflictError("Team is already registered for this event") from exc
    return registration


async def update_registration(
    db: AsyncSession, event_id: str, registration_id: str, data: dict
) -> EventRegistration:
    result = await db.execute(
        select(EventRegistration).where(
            EventRegistration.id == registration_id,
            EventRegistration.event_id == event_id,
        )
    )
    registration = result.scalar_one_or_none()
    if not registration:
        raise NotFoundError("Event registration not found")
    checked_in = data.pop("checked_in", None)
    for key, value in data.items():
        setattr(registration, key, value)
    if checked_in is not None:
        registration.checked_in_at = datetime.now(UTC) if checked_in else None
    return registration


async def remove_registration(db: AsyncSession, event_id: str, registration_id: str) -> None:
    registration = await update_registration(db, event_id, registration_id, {})
    await db.delete(registration)


async def list_phases(db: AsyncSession, event_id: str) -> list[EventPhase]:
    await get_event(db, event_id)
    result = await db.execute(
        select(EventPhase).where(EventPhase.event_id == event_id).order_by(EventPhase.sort_order)
    )
    return list(result.scalars().all())


async def create_phase(db: AsyncSession, event_id: str, data: dict) -> EventPhase:
    await get_event(db, event_id)
    phase = EventPhase(event_id=event_id, **data)
    db.add(phase)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise ConflictError("Another phase already uses this sort order") from exc
    return phase


async def update_phase(db: AsyncSession, event_id: str, phase_id: str, data: dict) -> EventPhase:
    result = await db.execute(
        select(EventPhase).where(EventPhase.id == phase_id, EventPhase.event_id == event_id)
    )
    phase = result.scalar_one_or_none()
    if not phase:
        raise NotFoundError("Event phase not found")
    for key, value in data.items():
        setattr(phase, key, value)
    if phase.starts_at and phase.ends_at and phase.ends_at <= phase.starts_at:
        raise ValidationError("ends_at must be after starts_at")
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise ConflictError("Another phase already uses this sort order") from exc
    return phase


async def delete_phase(db: AsyncSession, event_id: str, phase_id: str) -> None:
    phase = await update_phase(db, event_id, phase_id, {})
    if phase.status in ("live", "completed"):
        raise ConflictError("Live or completed phases cannot be deleted")
    await db.delete(phase)


async def list_scheduled_matches(
    db: AsyncSession, event_id: str, phase_id: str | None = None
) -> list[ScheduledMatch]:
    await get_event(db, event_id)
    query = (
        select(ScheduledMatch)
        .options(selectinload(ScheduledMatch.participants))
        .where(ScheduledMatch.event_id == event_id)
    )
    if phase_id:
        query = query.where(ScheduledMatch.phase_id == phase_id)
    result = await db.execute(
        query.order_by(ScheduledMatch.scheduled_at.nullslast(), ScheduledMatch.sequence_number)
    )
    return list(result.scalars().all())


def _seed_pairings(team_ids: list[str]) -> list[tuple[str, str | None]]:
    """Pair strongest against weakest and preserve a bye for odd fields."""
    pairings: list[tuple[str, str | None]] = []
    left, right = 0, len(team_ids) - 1
    while left <= right:
        pairings.append((team_ids[left], team_ids[right] if left != right else None))
        left += 1
        right -= 1
    return pairings


def _elimination_blueprint(team_ids: list[str], double_elimination: bool) -> list[dict]:
    """Create a linked winner bracket plus loser/final skeleton."""
    matches: list[dict[str, Any]] = []
    first_round = _seed_pairings(team_ids)
    winner_rounds: list[list[dict[str, Any]]] = []
    count = len(first_round)
    round_number = 1
    while count >= 1:
        round_matches: list[dict[str, Any]] = []
        for position in range(count):
            participants = []
            if round_number == 1:
                participants = [team for team in first_round[position] if team]
            item: dict[str, Any] = {
                "round_number": round_number,
                "bracket": "winner",
                "participants": participants,
                "position": position,
            }
            matches.append(item)
            round_matches.append(item)
        winner_rounds.append(round_matches)
        if count == 1:
            break
        count = (count + 1) // 2
        round_number += 1

    for index, current_round in enumerate(winner_rounds[:-1]):
        next_round = winner_rounds[index + 1]
        for item in current_round:
            item["next_winner"] = next_round[item["position"] // 2]

    if double_elimination and len(team_ids) > 2:
        loser_rounds: list[list[dict[str, Any]]] = []
        loser_count = max(1, len(first_round) // 2)
        loser_round_number = 1
        while loser_count >= 1:
            loser_round: list[dict[str, Any]] = []
            for position in range(loser_count):
                item = {
                    "round_number": loser_round_number,
                    "bracket": "loser",
                    "participants": [],
                    "position": position,
                }
                matches.append(item)
                loser_round.append(item)
            loser_rounds.append(loser_round)
            if loser_count == 1 and loser_round_number >= max(1, len(winner_rounds) - 1):
                break
            if loser_round_number % 2 == 0:
                loser_count = max(1, (loser_count + 1) // 2)
            loser_round_number += 1
        for index, loser_round in enumerate(loser_rounds[:-1]):
            next_round = loser_rounds[index + 1]
            for item in loser_round:
                item["next_winner"] = next_round[min(item["position"] // 2, len(next_round) - 1)]
        for index, winner_round in enumerate(winner_rounds[:-1]):
            loser_target = loser_rounds[min(index, len(loser_rounds) - 1)]
            for item in winner_round:
                item["next_loser"] = loser_target[min(item["position"] // 2, len(loser_target) - 1)]

        final: dict[str, Any] = {
            "round_number": len(winner_rounds) + 1,
            "bracket": "final",
            "participants": [],
            "position": 0,
        }
        matches.append(final)
        winner_rounds[-1][0]["next_winner"] = final
        loser_rounds[-1][0]["next_winner"] = final
    return matches


async def generate_schedule(db: AsyncSession, event_id: str, data: dict) -> list[ScheduledMatch]:
    event = await get_event(db, event_id)
    phase = await db.get(EventPhase, data["phase_id"])
    if not phase or phase.event_id != event_id:
        raise NotFoundError("Event phase not found")
    existing = await db.execute(
        select(ScheduledMatch.id).where(ScheduledMatch.phase_id == phase.id).limit(1)
    )
    if existing.scalar_one_or_none():
        if not data.get("replace_existing"):
            raise ConflictError("Phase already has a schedule")
        await db.execute(delete(ScheduledMatch).where(ScheduledMatch.phase_id == phase.id))
        await db.flush()

    registration_result = await db.execute(
        select(EventRegistration)
        .where(EventRegistration.event_id == event_id)
        .order_by(EventRegistration.seed_number.nullslast(), EventRegistration.registered_at)
    )
    registrations = list(registration_result.scalars().all())
    registered_ids = [registration.team_id for registration in registrations]
    team_ids = data.get("team_ids") or registered_ids
    unknown = set(team_ids) - set(registered_ids)
    if unknown:
        raise ValidationError("All scheduled teams must be registered for the event")
    if not team_ids:
        raise ValidationError("At least one registered team is required")

    if phase.phase_type in ("seeding", "double_seeding"):
        rounds = max(2, phase.rounds) if phase.phase_type == "double_seeding" else phase.rounds
        blueprint: list[dict[str, Any]] = [
            {
                "round_number": round_number,
                "bracket": "seeding",
                "participants": [team_id],
                "position": position,
            }
            for round_number in range(1, rounds + 1)
            for position, team_id in enumerate(team_ids)
        ]
    elif phase.phase_type == "double_elimination":
        blueprint = _elimination_blueprint(team_ids, True)
    else:
        blueprint = _elimination_blueprint(team_ids, False)

    table_count = data.get("table_count") or event.table_count
    start = data["starts_at"]
    slot_minutes = data["slot_minutes"]
    scheduled: list[ScheduledMatch] = []
    for sequence, item in enumerate(blueprint, start=1):
        slot_index = (sequence - 1) // table_count
        generated_match = ScheduledMatch(
            event_id=event_id,
            phase_id=phase.id,
            code=f"{phase.sort_order + 1}-{item['bracket'][0].upper()}{sequence}",
            round_number=item["round_number"],
            sequence_number=sequence,
            table_number=((sequence - 1) % table_count) + 1,
            scheduled_at=start + timedelta(minutes=slot_index * slot_minutes),
            duration_minutes=slot_minutes,
            bracket=item["bracket"],
        )
        db.add(generated_match)
        scheduled.append(generated_match)
        item["model"] = generated_match
    await db.flush()

    for item in blueprint:
        linked_match: ScheduledMatch = item["model"]
        if item.get("next_winner"):
            linked_match.next_winner_match_id = item["next_winner"]["model"].id
        if item.get("next_loser"):
            linked_match.next_loser_match_id = item["next_loser"]["model"].id
        for position, team_id in enumerate(item["participants"], start=1):
            db.add(
                MatchParticipant(
                    scheduled_match_id=linked_match.id,
                    team_id=team_id,
                    position=position,
                    side="red" if position == 1 else "blue",
                )
            )
    phase.status = "scheduled"
    await db.flush()
    return await list_scheduled_matches(db, event_id, phase.id)


async def update_scheduled_match(
    db: AsyncSession, event_id: str, match_id: str, data: dict
) -> ScheduledMatch:
    result = await db.execute(
        select(ScheduledMatch)
        .options(selectinload(ScheduledMatch.participants))
        .where(ScheduledMatch.id == match_id, ScheduledMatch.event_id == event_id)
    )
    match = result.scalar_one_or_none()
    if not match:
        raise NotFoundError("Scheduled match not found")
    expected_version = data.pop("expected_version")
    if match.version != expected_version:
        raise ConflictError(f"Schedule changed (current version: {match.version})")
    for key, value in data.items():
        setattr(match, key, value)
    if match.table_number and match.table_number > (await get_event(db, event_id)).table_count:
        raise ValidationError("Table number exceeds the configured table count")
    if match.scheduled_at and match.table_number:
        candidates = await list_scheduled_matches(db, event_id)
        own_teams = {
            participant.team_id for participant in match.participants if participant.team_id
        }
        start = match.scheduled_at
        end = start + timedelta(minutes=match.duration_minutes)
        for other in candidates:
            if other.id == match.id or not other.scheduled_at or other.status == "cancelled":
                continue
            other_end = other.scheduled_at + timedelta(minutes=other.duration_minutes)
            overlaps = start < other_end and other.scheduled_at < end
            other_teams = {
                participant.team_id for participant in other.participants if participant.team_id
            }
            if overlaps and other.table_number == match.table_number:
                raise ConflictError("Another match already uses this table and time slot")
            if overlaps and own_teams & other_teams:
                raise ConflictError("A team is already scheduled in this time slot")
    match.version += 1
    await db.flush()
    return match
