import random
import re
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.exceptions import ConflictError, NotFoundError, ValidationError
from modules.events import brackets
from modules.events.models import (
    Event,
    EventBracketWeight,
    EventPhase,
    EventRegistration,
    MatchParticipant,
    ScheduledMatch,
)
from modules.events.module_access import assert_phase_allowed, modules_for_season
from modules.scoring.competition_models import DEResult
from modules.scoring.models import Match, Ranking
from modules.seasons.lifecycle import ARCHIVED, DRAFT, ensure_writable
from modules.seasons.models import CompetitionLevel, Season
from modules.teams.models import Team, TeamSeasonRegistration


async def list_events(
    db: AsyncSession,
    season_id: str | None = None,
    status: str | None = None,
    limit: int | None = None,
    include_drafts: bool = True,
) -> list[Event]:
    query = select(Event).order_by(Event.starts_at.desc().nullslast(), Event.name)
    if not include_drafts:
        # Draft events, and every event of a draft season, are not visible to
        # users without events:write (guests, mentors).
        query = query.join(Season, Season.id == Event.season_id).where(
            Event.status != DRAFT, Season.status != DRAFT
        )
    if season_id:
        query = query.where(Event.season_id == season_id)
    if status:
        query = query.where(Event.status == status)
    if limit is not None:
        query = query.limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_event(db: AsyncSession, event_id: str, include_drafts: bool = True) -> Event:
    result = await db.execute(select(Event).where(Event.id == event_id))
    event = result.scalar_one_or_none()
    if not event:
        raise NotFoundError("Event not found")
    if not include_drafts:
        season_status = (
            await db.execute(select(Season.status).where(Season.id == event.season_id))
        ).scalar_one_or_none()
        if event.status == DRAFT or season_status == DRAFT:
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
    season = await db.get(Season, data["season_id"])
    if not season:
        raise NotFoundError("Season not found")
    await ensure_writable(db, season_id=data["season_id"])
    if data.get("active_modules") is None:
        data = {**data, "active_modules": modules_for_season(season)}
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
    # An archived event may only be taken out of the archive (status change).
    await ensure_writable(db, event_id=event_id, allow_archived_event=set(data) <= {"status"})
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
    if event.status == ARCHIVED:
        raise ConflictError("Archived events cannot be deleted")
    await ensure_writable(db, event_id=event_id)
    await db.delete(event)


async def list_registrations(db: AsyncSession, event_id: str) -> list[EventRegistration]:
    await get_event(db, event_id)
    result = await db.execute(
        select(EventRegistration)
        .options(selectinload(EventRegistration.team))
        .where(EventRegistration.event_id == event_id)
        .order_by(EventRegistration.seed_number.nullslast(), EventRegistration.registered_at)
    )
    return list(result.scalars().all())


async def add_registration(db: AsyncSession, event_id: str, data: dict) -> EventRegistration:
    event = await get_event(db, event_id)
    await ensure_writable(db, event_id=event_id)
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
    await db.refresh(registration, ["team"])
    return registration


async def ensure_legacy_default_registration(
    db: AsyncSession, event: Event, team_id: str
) -> EventRegistration:
    """Map a season-only legacy workflow to its generated default event.

    Explicit event APIs still require a pre-existing registration. This helper
    is only used when an older client omits ``event_id``.
    """
    result = await db.execute(
        select(EventRegistration).where(
            EventRegistration.event_id == event.id,
            EventRegistration.team_id == team_id,
        )
    )
    registration = result.scalar_one_or_none()
    if registration:
        return registration

    team = await db.get(Team, team_id)
    if not team:
        raise NotFoundError("Team not found")
    season_result = await db.execute(
        select(TeamSeasonRegistration).where(
            TeamSeasonRegistration.season_id == event.season_id,
            TeamSeasonRegistration.team_id == team_id,
        )
    )
    season_registration = season_result.scalar_one_or_none()
    if not season_registration:
        season_registration = TeamSeasonRegistration(
            season_id=event.season_id,
            team_id=team_id,
            competition_level_id=team.competition_level_id,
            category="botball",
        )
        db.add(season_registration)
        await db.flush()

    registration = EventRegistration(
        event_id=event.id,
        team_id=team_id,
        competition_level_id=season_registration.competition_level_id,
        category=season_registration.category,
    )
    db.add(registration)
    await db.flush()
    return registration


async def update_registration(
    db: AsyncSession, event_id: str, registration_id: str, data: dict
) -> EventRegistration:
    await ensure_writable(db, event_id=event_id)
    result = await db.execute(
        select(EventRegistration)
        .options(selectinload(EventRegistration.team))
        .where(
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
    event = await get_event(db, event_id)
    await ensure_writable(db, event_id=event_id)
    await assert_phase_allowed(db, event, data.get("phase_type", ""))
    phase = EventPhase(event_id=event_id, **data)
    db.add(phase)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise ConflictError("Another phase already uses this sort order") from exc
    return phase


async def update_phase(db: AsyncSession, event_id: str, phase_id: str, data: dict) -> EventPhase:
    await ensure_writable(db, event_id=event_id)
    result = await db.execute(
        select(EventPhase).where(EventPhase.id == phase_id, EventPhase.event_id == event_id)
    )
    phase = result.scalar_one_or_none()
    if not phase:
        raise NotFoundError("Event phase not found")
    if data.get("phase_type") and data["phase_type"] != phase.phase_type:
        # Switching a phase to a disabled module is the same as creating one.
        await assert_phase_allowed(db, await get_event(db, event_id), data["phase_type"])
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
        .options(selectinload(ScheduledMatch.participants).selectinload(MatchParticipant.team))
        .where(ScheduledMatch.event_id == event_id)
    )
    if phase_id:
        query = query.where(ScheduledMatch.phase_id == phase_id)
    result = await db.execute(
        query.order_by(ScheduledMatch.scheduled_at.nullslast(), ScheduledMatch.sequence_number)
    )
    return list(result.scalars().all())


ELIMINATION_PHASES = ("double_elimination", "final")
# DEResult.bracket is a single character (scoring.competition_models), so a
# bracket label is one letter: A, B, C, …
_BRACKET_LABEL = re.compile(r"^[A-Z]$")


def _seed_pairings(team_ids: list[str]) -> list[tuple[str | None, str | None]]:
    """First-round pairs in standard bracket order (see ``brackets.seed_pairings``)."""
    return brackets.seed_pairings(team_ids)


def _elimination_blueprint(team_ids: list[str], double_elimination: bool) -> list[dict]:
    """Schedule items for a seeded single or double elimination bracket."""
    try:
        nodes = brackets.elimination_blueprint(team_ids, double_elimination)
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    return [
        {
            "key": node.key,
            "label": node.key,
            "bracket": node.bracket,
            "round_number": node.round_number,
            "participants": dict(node.teams),
            "next_winner": node.next_winner,
            "next_winner_slot": node.next_winner_slot,
            "next_loser": node.next_loser,
            "next_loser_slot": node.next_loser_slot,
            "wave": node.depth,
        }
        for node in nodes
    ]


def _seeding_blueprint(team_ids: list[str], rounds: int) -> list[dict]:
    """One solo run per team and round."""
    return [
        {
            "bracket": "seeding",
            "round_number": round_number,
            "participants": {1: team_id},
            "wave": round_number,
        }
        for round_number in range(1, rounds + 1)
        for team_id in team_ids
    ]


def _double_seeding_blueprint(team_ids: list[str], rounds: int) -> list[dict]:
    """Head-to-head seeding: two teams share a table, every run counts.

    Opponents rotate from round to round (circle method), and the sides swap
    every other round so each team runs from both starting positions. With an
    odd field one team per round runs alone.
    """
    field: list[str | None] = list(team_ids)
    if len(field) % 2:
        field.append(None)
    items: list[dict] = []
    for round_index in range(rounds):
        half = len(field) // 2
        for index in range(half):
            first, second = field[index], field[-1 - index]
            if round_index % 2:
                first, second = second, first
            teams = [team for team in (first, second) if team]
            items.append(
                {
                    "bracket": "double_seeding",
                    "round_number": round_index + 1,
                    "participants": {
                        position: team for position, team in enumerate(teams, start=1)
                    },
                    "wave": round_index + 1,
                }
            )
        # Rotate every team but the first one position clockwise.
        if len(field) > 2:
            field = [field[0], field[-1], *field[1:-1]]
    return items


def _form_alliances(phase: EventPhase, team_ids: list[str]) -> list[list[str]]:
    """Alliance partners: assigned in the phase settings, balanced by seed, or drawn.

    ``settings.alliance_mode``:
    * ``assigned`` – ``settings.alliances`` lists the pairs explicitly;
    * ``seeded`` – seed 1 with the last seed, 2 with the second-to-last, …;
    * ``draw`` (default) – a random draw, reproducible via ``draw_seed``.
    The result is stored in ``settings.alliances``. With an odd field the last
    alliance has a single team.
    """
    settings = dict(phase.settings or {})
    mode = settings.get("alliance_mode", "draw")
    if mode == "assigned":
        alliances = [list(group) for group in settings.get("alliances") or []]
        flat = [team for group in alliances for team in group]
        if any(not 1 <= len(group) <= 2 for group in alliances):
            raise ValidationError("An alliance consists of one or two teams")
        if len(flat) != len(set(flat)) or set(flat) != set(team_ids):
            raise ValidationError("Every scheduled team must be in exactly one alliance")
        return alliances
    if mode == "seeded":
        ordered = list(team_ids)
        alliances = []
        while ordered:
            group = [ordered.pop(0)]
            if ordered:
                group.append(ordered.pop())
            alliances.append(group)
    elif mode == "draw":
        draw_seed = settings.get("draw_seed") or secrets.randbits(32)
        shuffled = list(team_ids)
        random.Random(draw_seed).shuffle(shuffled)
        alliances = [shuffled[index : index + 2] for index in range(0, len(shuffled), 2)]
        settings["draw_seed"] = draw_seed
    else:
        raise ValidationError("alliance_mode must be 'assigned', 'seeded' or 'draw'")
    settings["alliances"] = alliances
    phase.settings = settings
    return alliances


def _alliance_blueprint(alliances: list[list[str]], rounds: int) -> list[dict]:
    """Each alliance plays ``rounds`` runs together; its score is the sum of both sides."""
    return [
        {
            "bracket": "alliance",
            "round_number": round_number,
            "participants": {position: team for position, team in enumerate(group, start=1)},
            "side": f"alliance-{index + 1}",
            "wave": round_number,
        }
        for round_number in range(1, rounds + 1)
        for index, group in enumerate(alliances)
    ]


def _bracket_label(phase: EventPhase) -> str:
    label = str((phase.settings or {}).get("bracket_label", "A")).upper()
    if not _BRACKET_LABEL.match(label):
        raise ValidationError("bracket_label must be a single letter (A, B, C, …)")
    return label


async def _phase_team_ids(
    db: AsyncSession, event_id: str, phase: EventPhase, data: dict
) -> list[str]:
    """Registered teams for a phase, ordered by seed (category-filtered)."""
    query = select(EventRegistration).where(EventRegistration.event_id == event_id)
    category = data.get("category") or (phase.settings or {}).get("category")
    if category:
        query = query.where(EventRegistration.category == category)
    registration_result = await db.execute(
        query.order_by(EventRegistration.seed_number.nullslast(), EventRegistration.registered_at)
    )
    registered_ids = [registration.team_id for registration in registration_result.scalars()]
    requested = data.get("team_ids")
    if not requested:
        return registered_ids
    unknown = set(requested) - set(registered_ids)
    if unknown:
        raise ValidationError("All scheduled teams must be registered for the event")
    if phase.phase_type in ELIMINATION_PHASES:
        # Brackets are seeded: the registration seed decides, not the list order.
        wanted = set(requested)
        return [team_id for team_id in registered_ids if team_id in wanted]
    return list(dict.fromkeys(requested))


async def generate_schedule(db: AsyncSession, event_id: str, data: dict) -> list[ScheduledMatch]:
    event = await get_event(db, event_id)
    await ensure_writable(db, event_id=event_id)
    phase = await db.get(EventPhase, data["phase_id"])
    if not phase or phase.event_id != event_id:
        raise NotFoundError("Event phase not found")
    await assert_phase_allowed(db, event, phase.phase_type)
    existing = await db.execute(
        select(ScheduledMatch.id).where(ScheduledMatch.phase_id == phase.id).limit(1)
    )
    if existing.scalar_one_or_none():
        if not data.get("replace_existing"):
            raise ConflictError("Phase already has a schedule")
        await db.execute(delete(ScheduledMatch).where(ScheduledMatch.phase_id == phase.id))
        await db.flush()

    team_ids = await _phase_team_ids(db, event_id, phase, data)
    if not team_ids:
        raise ValidationError("At least one registered team is required")

    blueprint: list[dict[str, Any]]
    if phase.phase_type == "seeding":
        blueprint = _seeding_blueprint(team_ids, phase.rounds)
    elif phase.phase_type == "double_seeding":
        blueprint = _double_seeding_blueprint(team_ids, max(2, phase.rounds))
    elif phase.phase_type == "alliance":
        blueprint = _alliance_blueprint(_form_alliances(phase, team_ids), phase.rounds)
    elif phase.phase_type == "double_elimination":
        label = _bracket_label(phase)
        blueprint = _elimination_blueprint(team_ids, True)
        # A regenerated bracket starts over: drop the placements of the old one.
        await db.execute(
            delete(DEResult).where(DEResult.event_id == event_id, DEResult.bracket == label)
        )
    else:
        blueprint = _elimination_blueprint(team_ids, False)

    table_count = data.get("table_count") or event.table_count
    start = data["starts_at"]
    slot_minutes = data["slot_minutes"]
    # Matches of one wave may run in parallel; a match never shares a time slot
    # with a match it depends on (or with an earlier round of the same team).
    ordered = sorted(enumerate(blueprint), key=lambda pair: (pair[1]["wave"], pair[0]))
    slot_index, table_index, current_wave = -1, table_count, None
    by_key: dict[str, ScheduledMatch] = {}
    for sequence, (_, item) in enumerate(ordered, start=1):
        if item["wave"] != current_wave or table_index >= table_count:
            slot_index += 1
            table_index = 0
            current_wave = item["wave"]
        label = item.get("label") or f"{item['bracket'][0].upper()}{sequence}"
        generated_match = ScheduledMatch(
            event_id=event_id,
            phase_id=phase.id,
            code=f"{phase.sort_order + 1}-{label}",
            round_number=item["round_number"],
            sequence_number=sequence,
            table_number=table_index + 1,
            scheduled_at=start + timedelta(minutes=slot_index * slot_minutes),
            duration_minutes=slot_minutes,
            bracket=item["bracket"],
            next_winner_slot=item.get("next_winner_slot"),
            next_loser_slot=item.get("next_loser_slot"),
        )
        table_index += 1
        db.add(generated_match)
        item["model"] = generated_match
        if item.get("key"):
            by_key[item["key"]] = generated_match
    await db.flush()

    for item in blueprint:
        linked_match: ScheduledMatch = item["model"]
        if item.get("next_winner"):
            linked_match.next_winner_match_id = by_key[item["next_winner"]].id
        if item.get("next_loser"):
            linked_match.next_loser_match_id = by_key[item["next_loser"]].id
        for position, team_id in sorted(item["participants"].items()):
            db.add(
                MatchParticipant(
                    scheduled_match_id=linked_match.id,
                    team_id=team_id,
                    position=position,
                    side=item.get("side") or _side(position),
                )
            )
    phase.status = "scheduled"
    await db.flush()
    return await list_scheduled_matches(db, event_id, phase.id)


def _side(position: int) -> str:
    return "red" if position == 1 else "blue"


# ── Seeds from the seeding ranking ────────────────────────────────────────────


async def assign_seeds_from_seeding(
    db: AsyncSession,
    event_id: str,
    category: str | None = None,
    phase_id: str | None = None,
) -> list[EventRegistration]:
    """Number the registrations 1..n per category in seeding-ranking order.

    The ranking comes from the given seeding phase, or from all seeding and
    double-seeding phases (plus scores without a phase) of the event. Teams
    without a seeding score follow in registration order. Only ``category``
    is renumbered when given.
    """
    await ensure_writable(db, event_id=event_id)
    registrations = await list_registrations(db, event_id)
    query = select(Ranking).where(Ranking.event_id == event_id)
    if phase_id:
        phase = await db.get(EventPhase, phase_id)
        if not phase or phase.event_id != event_id:
            raise NotFoundError("Event phase not found")
        query = query.where(Ranking.event_phase_id == phase_id)
    else:
        seeding_phases = select(EventPhase.id).where(
            EventPhase.event_id == event_id,
            EventPhase.phase_type.in_(("seeding", "double_seeding")),
        )
        query = query.where(
            Ranking.event_phase_id.is_(None) | Ranking.event_phase_id.in_(seeding_phases)
        )
    best: dict[str, Ranking] = {}
    for ranking in (await db.execute(query)).scalars():
        current = best.get(ranking.team_id)
        if current is None or ranking.seed_score > current.seed_score:
            best[ranking.team_id] = ranking

    categories = sorted({registration.category for registration in registrations})
    for current_category in categories:
        if category and current_category != category:
            continue
        group = [item for item in registrations if item.category == current_category]
        ranked = sorted(
            (item for item in group if item.team_id in best),
            key=lambda item: (
                -best[item.team_id].seed_score,
                -best[item.team_id].best_score,
                item.team.name,
            ),
        )
        unranked = sorted(
            (item for item in group if item.team_id not in best),
            key=lambda item: item.registered_at,
        )
        for seed, registration in enumerate([*ranked, *unranked], start=1):
            registration.seed_number = seed
    await db.flush()
    return await list_registrations(db, event_id)


# ── Results and bracket advancement ───────────────────────────────────────────


async def _load_match(db: AsyncSession, event_id: str, match_id: str) -> ScheduledMatch:
    result = await db.execute(
        select(ScheduledMatch)
        .options(selectinload(ScheduledMatch.participants).selectinload(MatchParticipant.team))
        .where(ScheduledMatch.id == match_id, ScheduledMatch.event_id == event_id)
        .execution_options(populate_existing=True)
    )
    match = result.scalar_one_or_none()
    if not match:
        raise NotFoundError("Scheduled match not found")
    return match


def _is_grand_final(match: ScheduledMatch) -> bool:
    return match.bracket == brackets.FINAL and match.round_number == 1


def _is_reset_final(match: ScheduledMatch) -> bool:
    return match.bracket == brackets.FINAL and match.round_number == 2


async def _place_team(
    db: AsyncSession, event_id: str, match_id: str, position: int, team_id: str
) -> None:
    target = await _load_match(db, event_id, match_id)
    if target.status == "completed":
        raise ConflictError(f"Match {target.code} is already completed")
    for participant in target.participants:
        if participant.position == position:
            participant.team_id = team_id
            participant.result = None
            participant.score = None
            return
    db.add(
        MatchParticipant(
            scheduled_match_id=target.id,
            team_id=team_id,
            position=position,
            side=_side(position),
        )
    )


async def _remove_team(db: AsyncSession, event_id: str, match_id: str, team_id: str) -> None:
    target = await _load_match(db, event_id, match_id)
    if target.status == "completed":
        raise ConflictError(
            f"Match {target.code} was already played with this team; correct it first"
        )
    for participant in list(target.participants):
        if participant.team_id == team_id:
            await db.delete(participant)
    await db.flush()


async def _undo_advancement(
    db: AsyncSession, event_id: str, match: ScheduledMatch, winner: str, loser: str
) -> None:
    """Take a previously recorded result back out of the downstream matches."""
    if _is_grand_final(match):
        if match.next_winner_match_id:
            reset = await _load_match(db, event_id, match.next_winner_match_id)
            if reset.status == "completed":
                raise ConflictError("The reset final was already played; correct it first")
            for participant in list(reset.participants):
                await db.delete(participant)
            reset.status = "scheduled"
            await db.flush()
        return
    if match.next_winner_match_id:
        await _remove_team(db, event_id, match.next_winner_match_id, winner)
    if match.next_loser_match_id:
        await _remove_team(db, event_id, match.next_loser_match_id, loser)


async def _advance(
    db: AsyncSession, event_id: str, match: ScheduledMatch, winner: MatchParticipant, loser
) -> None:
    if _is_reset_final(match):
        return
    if _is_grand_final(match):
        if not match.next_winner_match_id:
            return
        reset = await _load_match(db, event_id, match.next_winner_match_id)
        if winner.position == 1:
            # The winner-bracket champion is still unbeaten: the tournament is
            # over and the reset final is not needed.
            reset.status = "cancelled"
            return
        # First loss for the winner-bracket side: both play the reset final,
        # winner-bracket side again in position 1.
        reset.status = "scheduled"
        first = winner if winner.position == 1 else loser
        second = loser if first is winner else winner
        await _place_team(db, event_id, reset.id, 1, str(first.team_id))
        await _place_team(db, event_id, reset.id, 2, str(second.team_id))
        return
    if match.next_winner_match_id:
        await _place_team(
            db,
            event_id,
            match.next_winner_match_id,
            match.next_winner_slot or 1,
            str(winner.team_id),
        )
    if match.next_loser_match_id:
        await _place_team(
            db,
            event_id,
            match.next_loser_match_id,
            match.next_loser_slot or 1,
            str(loser.team_id),
        )


async def record_match_result(
    db: AsyncSession, event_id: str, match_id: str, data: dict
) -> ScheduledMatch:
    """Record the outcome of a scheduled match.

    Elimination matches need the winner: the winner moves to
    ``next_winner_match``, the loser to ``next_loser_match`` or is out; the
    grand final either ends the bracket or fills the reset final. A different
    winner for an already completed match is accepted as a correction as long
    as the matches it fed into have not been played yet. Other phases record
    per-team scores (alliance score = sum of both sides).
    """
    await ensure_writable(db, event_id=event_id)
    event = await get_event(db, event_id)
    match = await _load_match(db, event_id, match_id)
    expected_version = data.get("expected_version")
    if expected_version is not None and expected_version != match.version:
        raise ConflictError(f"Schedule changed (current version: {match.version})")
    if match.status == "cancelled":
        raise ConflictError("Cancelled matches have no result")
    phase = await db.get(EventPhase, match.phase_id)
    if phase is None:
        raise NotFoundError("Event phase not found")
    by_team = {p.team_id: p for p in match.participants if p.team_id}

    scores: dict[str, float] = data.get("scores") or {}
    if set(scores) - set(by_team):
        raise ValidationError("Scores can only be recorded for the teams in this match")
    previous_scores = {team_id: by_team[team_id].score for team_id in scores}
    for team_id, score in scores.items():
        by_team[team_id].score = score

    corrected = match.status == "completed" and any(
        previous_scores[team_id] != score for team_id, score in scores.items()
    )
    if phase.phase_type in ELIMINATION_PHASES:
        winner_id = data.get("winner_team_id")
        if len(by_team) != 2:
            raise ValidationError("Both teams of this match must be known first")
        if winner_id not in by_team:
            raise ValidationError("The winner must be one of the two teams in this match")
        winner = by_team[winner_id]
        loser = next(p for p in by_team.values() if p.team_id != winner_id)
        previous_winner = next((p for p in by_team.values() if p.result == "win"), None)
        if match.status == "completed" and previous_winner:
            if previous_winner.team_id != winner_id:
                await _undo_advancement(
                    db, event_id, match, str(previous_winner.team_id), str(winner_id)
                )
                corrected = True
                winner.result, loser.result = "win", "loss"
                await _advance(db, event_id, match, winner, loser)
        else:
            winner.result, loser.result = "win", "loss"
            await _advance(db, event_id, match, winner, loser)
    elif not scores and match.status != "completed":
        raise ValidationError("Scores are required for this match")

    match.status = "completed"
    match.version += 1
    await db.flush()
    if phase.phase_type == "double_elimination":
        await sync_de_results(db, event, phase)
    elif phase.phase_type == "final":
        await _complete_if_decided(db, phase)
    if corrected:
        from modules.events.notifications import notify_result_corrected

        await notify_result_corrected(db, event_id, match)
    return await _load_match(db, event_id, match.id)


async def _phase_outcomes(
    db: AsyncSession, phase: EventPhase
) -> tuple[list[brackets.MatchOutcome], set[str]]:
    result = await db.execute(
        select(ScheduledMatch)
        .options(selectinload(ScheduledMatch.participants))
        .where(ScheduledMatch.phase_id == phase.id)
        .execution_options(populate_existing=True)
    )
    outcomes: list[brackets.MatchOutcome] = []
    teams: set[str] = set()
    for match in result.scalars():
        winner = next((p for p in match.participants if p.result == "win"), None)
        loser = next((p for p in match.participants if p.result == "loss"), None)
        teams.update(p.team_id for p in match.participants if p.team_id)
        if _is_grand_final(match):
            key = "GF"
        elif _is_reset_final(match):
            key = "GF2"
        else:
            key = match.id
        outcomes.append(
            brackets.MatchOutcome(
                key=key,
                bracket=match.bracket or brackets.WINNER,
                round_number=match.round_number,
                next_loser=match.next_loser_match_id,
                winner=winner.team_id if winner else None,
                loser=loser.team_id if loser else None,
                winner_position=winner.position if winner else None,
                completed=match.status == "completed",
                cancelled=match.status == "cancelled",
            )
        )
    return outcomes, teams


async def phase_placements(db: AsyncSession, phase: EventPhase) -> dict[str, int]:
    outcomes, teams = await _phase_outcomes(db, phase)
    if not outcomes:
        return {}
    return brackets.elimination_placements(outcomes, len(teams))


async def _complete_if_decided(db: AsyncSession, phase: EventPhase) -> dict[str, int]:
    places = await phase_placements(db, phase)
    if 1 in places.values():
        phase.status = "completed"
    elif phase.status in ("draft", "scheduled"):
        phase.status = "live"
    return places


async def sync_de_results(db: AsyncSession, event: Event, phase: EventPhase) -> None:
    """Write the placements of a double-elimination phase into ``de_results``.

    ``bracket_score`` follows the manual DE entry (1 for the winner down to 0
    for last place); the DE score itself is left to the scoring formula.
    """
    label = _bracket_label(phase)
    places = await _complete_if_decided(db, phase)
    _, teams = await _phase_outcomes(db, phase)
    field = len(teams)
    existing = {
        row.team_id: row
        for row in (
            await db.execute(select(DEResult).where(DEResult.event_id == event.id))
        ).scalars()
    }
    for team_id in teams:
        rank = places.get(team_id)
        row = existing.get(team_id)
        if row is None:
            if rank is None:
                continue
            row = DEResult(season_id=event.season_id, event_id=event.id, team_id=team_id)
            db.add(row)
        row.bracket = label
        row.de_rank = rank
        row.bracket_score = (
            None if rank is None else (1.0 if field <= 1 else 1 - (rank - 1) / (field - 1))
        )
    await db.flush()


# ── Bracket view, alliance standings, bracket weights ─────────────────────────


async def get_brackets(db: AsyncSession, event_id: str) -> list[dict]:
    """Every elimination phase with its matches and the placements known so far."""
    phases = [
        phase for phase in await list_phases(db, event_id) if phase.phase_type in ELIMINATION_PHASES
    ]
    all_matches = await list_scheduled_matches(db, event_id)
    names: dict[str, tuple[str, str | None]] = {}
    for match in all_matches:
        for participant in match.participants:
            if participant.team_id and participant.team:
                names[participant.team_id] = (
                    participant.team.name,
                    participant.team.team_number,
                )
    output = []
    for phase in phases:
        places = await phase_placements(db, phase)
        output.append(
            {
                "phase_id": phase.id,
                "phase_name": phase.name,
                "phase_type": phase.phase_type,
                "status": phase.status,
                "bracket_label": (phase.settings or {}).get("bracket_label", "A"),
                "matches": sorted(
                    (match for match in all_matches if match.phase_id == phase.id),
                    key=lambda match: match.sequence_number,
                ),
                "placements": sorted(
                    (
                        {
                            "team_id": team_id,
                            "team_name": names.get(team_id, ("", None))[0],
                            "team_number": names.get(team_id, ("", None))[1],
                            "rank": rank,
                        }
                        for team_id, rank in places.items()
                    ),
                    key=lambda item: (item["rank"], item["team_name"]),
                ),
            }
        )
    return output


async def alliance_standings(db: AsyncSession, event_id: str, phase_id: str) -> list[dict]:
    """Alliance ranking: per run, the alliance score is the sum of both teams.

    A team's score in a run is the score recorded on the scheduled match or,
    if none was recorded there, its official score entry for that match
    (disqualified runs count 0, negative scores count 0). Alliances are
    ranked by their best run, then by the total of all runs.
    """
    phase = await db.get(EventPhase, phase_id)
    if not phase or phase.event_id != event_id or phase.phase_type != "alliance":
        raise NotFoundError("Alliance phase not found")
    matches = await list_scheduled_matches(db, event_id, phase_id)
    entered: dict[tuple[str, str], float] = {}
    if matches:
        rows = await db.execute(
            select(Match).where(
                Match.scheduled_match_id.in_([match.id for match in matches]),
                Match.is_practice.is_(False),
            )
        )
        for row in rows.scalars():
            value = 0.0 if row.is_disqualified else max(0.0, float(row.total_score or 0.0))
            key = (str(row.scheduled_match_id), row.team_id)
            entered[key] = max(entered.get(key, 0.0), value)

    alliances: dict[tuple[str, ...], dict[str, Any]] = {}
    for match in matches:
        members = sorted((p for p in match.participants if p.team_id), key=lambda p: p.position)
        if not members:
            continue
        alliance_key = tuple(str(p.team_id) for p in members)
        entry = alliances.setdefault(
            alliance_key,
            {
                "team_ids": list(alliance_key),
                "team_names": [p.team_name or "" for p in members],
                "runs": [],
            },
        )
        run_scores = []
        for participant in members:
            if participant.score is not None:
                run_scores.append(max(0.0, float(participant.score)))
            elif (match.id, str(participant.team_id)) in entered:
                run_scores.append(entered[(match.id, str(participant.team_id))])
        if run_scores:
            entry["runs"].append(
                {"match_id": match.id, "round_number": match.round_number, "score": sum(run_scores)}
            )
    standings = []
    for entry in alliances.values():
        values = [run["score"] for run in entry["runs"]]
        entry["best_score"] = max(values) if values else 0.0
        entry["total_score"] = sum(values)
        standings.append(entry)
    standings.sort(key=lambda item: (-item["best_score"], -item["total_score"]))
    for rank, entry in enumerate(standings, start=1):
        entry["rank"] = rank
    return standings


async def get_bracket_weights(
    db: AsyncSession, event_id: str, category: str = "botball"
) -> dict[str, float]:
    """Bracket weights of an event, falling back to the season-wide weights."""
    event = await get_event(db, event_id)
    result = await db.execute(
        select(EventBracketWeight).where(
            EventBracketWeight.event_id == event_id,
            EventBracketWeight.category == category,
        )
    )
    weights = {row.bracket: row.weight for row in result.scalars()}
    if weights:
        return weights
    from modules.scoring.formula_service import get_bracket_weights as season_weights

    return await season_weights(db, event.season_id, category)


async def set_bracket_weights(
    db: AsyncSession, event_id: str, category: str, weights: dict[str, float]
) -> dict[str, float]:
    await ensure_writable(db, event_id=event_id)
    await get_event(db, event_id)
    await db.execute(
        delete(EventBracketWeight).where(
            EventBracketWeight.event_id == event_id,
            EventBracketWeight.category == category,
        )
    )
    db.add_all(
        EventBracketWeight(event_id=event_id, category=category, bracket=bracket, weight=weight)
        for bracket, weight in weights.items()
    )
    await db.flush()
    return dict(weights)


async def update_scheduled_match(
    db: AsyncSession, event_id: str, match_id: str, data: dict
) -> ScheduledMatch:
    await ensure_writable(db, event_id=event_id)
    result = await db.execute(
        select(ScheduledMatch)
        .options(selectinload(ScheduledMatch.participants).selectinload(MatchParticipant.team))
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
