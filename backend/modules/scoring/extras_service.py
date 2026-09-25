"""Rules, schema templates/cloning, head-to-head outcomes, DE placement,
parts challenges, scouting and GCER qualification."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import has_elevated_access, own_team_ids
from core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from modules.events.models import Event, EventPhase, EventRegistration, ScheduledMatch
from modules.scoring import rules_service, sheet, tiebreak
from modules.scoring import service as score_service
from modules.scoring.competition_models import DEResult
from modules.scoring.extras_models import (
    ExternalTeam,
    PartsChallenge,
    ScoringRuleSet,
    ScoutingNote,
    ScoutingObservation,
    TeamQualification,
)
from modules.scoring.models import Ranking, ScoringSchema
from modules.seasons.lifecycle import ensure_writable
from modules.seasons.models import CompetitionLevel, Season
from modules.teams.models import Team

ORGANIZER = "scoring:admin"


# ── Season rules ──────────────────────────────────────────────────────────────


async def get_rule_set(db: AsyncSession, season_id: str) -> dict[str, Any]:
    if not await db.get(Season, season_id):
        raise NotFoundError("Season not found")
    rules = await rules_service.get_rules(db, season_id)
    return {
        "season_id": season_id,
        "tiebreakers": rules.tiebreakers,
        "finals_replay": rules.finals_replay,
        "end_contact_bonus_percent": rules.end_contact_bonus_percent,
        "referee_checklist": rules.referee_checklist,
    }


async def put_rule_set(db: AsyncSession, season_id: str, data: dict[str, Any]) -> dict[str, Any]:
    if not await db.get(Season, season_id):
        raise NotFoundError("Season not found")
    await ensure_writable(db, season_id=season_id)
    result = await db.execute(select(ScoringRuleSet).where(ScoringRuleSet.season_id == season_id))
    row = result.scalar_one_or_none()
    if row is None:
        row = ScoringRuleSet(season_id=season_id)
        db.add(row)
    row.tiebreakers = data["tiebreakers"]
    row.finals_replay = data["finals_replay"]
    row.end_contact_bonus_percent = data["end_contact_bonus_percent"]
    row.referee_checklist = data["referee_checklist"]
    await db.flush()
    # Tie-breakers decide shared seed scores: re-rank every event of the season.
    for event_id in await season_event_ids(db, season_id):
        await score_service.refresh_all_levels(db, event_id)
    return await get_rule_set(db, season_id)


async def season_event_ids(db: AsyncSession, season_id: str) -> list[str]:
    result = await db.execute(select(Event.id).where(Event.season_id == season_id))
    return list(result.scalars())


def tiebreaker_presets() -> list[dict[str, Any]]:
    return [{"id": key, **deepcopy(value)} for key, value in tiebreak.TIEBREAKER_PRESETS.items()]


# ── Schemas: listing and cloning ──────────────────────────────────────────────


async def list_schemas(db: AsyncSession, season_id: str | None = None) -> list[dict[str, Any]]:
    """Active schema versions of all events (or one season) — the clone sources."""
    query = (
        select(ScoringSchema, Event.name, Season.name, CompetitionLevel.name)
        .join(Season, Season.id == ScoringSchema.season_id)
        .outerjoin(Event, Event.id == ScoringSchema.event_id)
        .outerjoin(CompetitionLevel, CompetitionLevel.id == ScoringSchema.competition_level_id)
        .where(ScoringSchema.is_active.is_(True))
        .order_by(Season.year.desc(), Event.name, ScoringSchema.version.desc())
    )
    if season_id:
        query = query.where(ScoringSchema.season_id == season_id)
    rows = (await db.execute(query)).all()
    return [
        {
            "id": schema.id,
            "season_id": schema.season_id,
            "season_name": season_name,
            "event_id": schema.event_id,
            "event_name": event_name,
            "competition_level_id": schema.competition_level_id,
            "competition_level_name": level_name,
            "version": schema.version,
            "structured": sheet.is_structured(schema.definition),
            "field_count": len(schema.fields or []),
        }
        for schema, event_name, season_name, level_name in rows
    ]


async def clone_schema(
    db: AsyncSession,
    event_id: str,
    source_schema_id: str,
    competition_level_id: str | None,
    activate: bool,
) -> ScoringSchema:
    """Copy another schema (e.g. ECER's) as a new, independent version for this event."""
    event = await db.get(Event, event_id)
    if not event:
        raise NotFoundError("Event not found")
    await ensure_writable(db, event_id=event_id)
    source = await db.get(ScoringSchema, source_schema_id)
    if not source:
        raise NotFoundError("Source scoring schema not found")
    if competition_level_id and not await db.get(CompetitionLevel, competition_level_id):
        raise NotFoundError("Competition level not found")
    definition = deepcopy(source.definition) if sheet.is_structured(source.definition) else None
    return await score_service.create_schema_version(
        db,
        event,
        competition_level_id,
        deepcopy(source.fields or []),
        activate,
        definition,
    )


# ── Head to head ──────────────────────────────────────────────────────────────


async def _team_names(db: AsyncSession, team_ids: set[str]) -> dict[str, Team]:
    if not team_ids:
        return {}
    result = await db.execute(select(Team).where(Team.id.in_(team_ids)))
    return {team.id: team for team in result.scalars()}


async def head_to_head_outcome(db: AsyncSession, scheduled_match_id: str) -> dict[str, Any]:
    """Who won a head-to-head match and why (score, tie-breaker, DQ, …)."""
    scheduled = await db.get(ScheduledMatch, scheduled_match_id)
    if not scheduled:
        raise NotFoundError("Scheduled match not found")
    event = await db.get(Event, scheduled.event_id)
    matches = await rules_service.head_to_head_matches(db, scheduled_match_id)
    names = await _team_names(db, {m.team_id for m in matches})
    sides = [
        {
            "match_id": m.id,
            "team_id": m.team_id,
            "team_name": names[m.team_id].name if m.team_id in names else None,
            "sheet_score": m.sheet_score,
            "bonus_score": m.bonus_score,
            "total_score": m.total_score,
            "is_disqualified": m.is_disqualified,
            "round_lost": m.round_lost,
            "round_lost_reason": m.round_lost_reason,
            "end_contact": m.end_contact,
        }
        for m in matches
    ]
    base = {"scheduled_match_id": scheduled_match_id, "sides": sides}
    if len(matches) != 2 or not event:
        return {**base, "winner": None, "reason": "incomplete", "decided_by": None, "replay": False}
    rules = await rules_service.get_rules(db, event.season_id)
    phase = await db.get(EventPhase, scheduled.phase_id)
    is_final = scheduled.bracket == "final" or bool(phase and phase.phase_type == "final")
    replayed = any(bool((m.tiebreak_values or {}).get(tiebreak.REPLAYED_KEY)) for m in matches)
    outcome = tiebreak.decide_head_to_head(
        rules_service.contestant(matches[0], rules.tiebreakers),
        rules_service.contestant(matches[1], rules.tiebreakers),
        rules.tiebreakers,
        is_final=is_final,
        finals_replay=rules.finals_replay,
        replayed=replayed,
    )
    return {**base, **outcome.as_dict()}


async def de_placement(db: AsyncSession, event_id: str) -> list[dict[str, Any]]:
    """DE placement per bracket; equal DE ranks are ordered by the tie-breakers.

    The DE ranks come from ``de_results`` — written by the bracket
    (events.service.sync_de_results) or entered by hand on the DE page. The
    ordering itself is events.service.tiebroken_placements, the same one the
    bracket view uses: a tie-breaker's value for a team is summed over its
    scored runs in the bracket's elimination phases; the seeding rank is the
    last resort.
    """
    from modules.events import service as event_service

    event = await db.get(Event, event_id)
    if not event:
        raise NotFoundError("Event not found")
    rows = list((await db.execute(select(DEResult).where(DEResult.event_id == event_id))).scalars())
    if not rows:
        return []
    names = await _team_names(db, {r.team_id for r in rows})

    # Phases per bracket label; a manual DE entry without a bracket phase uses
    # the runs of every elimination phase of the event.
    phases = (
        await db.execute(
            select(EventPhase).where(
                EventPhase.event_id == event_id,
                EventPhase.phase_type.in_(event_service.ELIMINATION_PHASES),
            )
        )
    ).scalars()
    by_label: dict[str, set[str]] = {}
    all_phase_ids: set[str] = set()
    for phase in phases:
        label = str((phase.settings or {}).get("bracket_label", "A")).upper()
        by_label.setdefault(label, set()).add(phase.id)
        all_phase_ids.add(phase.id)

    out: list[dict[str, Any]] = []
    for bracket in sorted({r.bracket for r in rows}):
        in_bracket = [r for r in rows if r.bracket == bracket]
        places = {r.team_id: r.de_rank for r in in_bracket if r.de_rank}
        ordered = await event_service.tiebroken_placements(
            db, event, places, by_label.get(str(bracket).upper(), all_phase_ids)
        )
        # Teams still in the bracket (no DE rank yet) follow the placed ones.
        placed = len(ordered)
        ordered += [
            {"team_id": r.team_id, "de_rank": None, "placement": placed + 1, "decided_by": None}
            for r in sorted(in_bracket, key=lambda r: r.team_id)
            if not r.de_rank
        ]
        for row in ordered:
            out.append(
                {
                    "bracket": bracket,
                    "team_name": names[row["team_id"]].name if row["team_id"] in names else None,
                    **row,
                }
            )
    return out


# ── Parts challenges ──────────────────────────────────────────────────────────


async def list_parts_challenges(db: AsyncSession, event_id: str) -> list[PartsChallenge]:
    result = await db.execute(
        select(PartsChallenge)
        .where(PartsChallenge.event_id == event_id)
        .order_by(PartsChallenge.created_at)
    )
    return list(result.scalars())


async def create_parts_challenge(
    db: AsyncSession, event_id: str, data: dict[str, Any], user_id: str
) -> PartsChallenge:
    if not await db.get(Event, event_id):
        raise NotFoundError("Event not found")
    await ensure_writable(db, event_id=event_id)
    if data.get("scheduled_match_id"):
        scheduled = await db.get(ScheduledMatch, data["scheduled_match_id"])
        if not scheduled or scheduled.event_id != event_id:
            raise ValidationError("Scheduled match does not belong to this event")
    challenge = PartsChallenge(event_id=event_id, created_by=user_id, **data)
    db.add(challenge)
    await db.flush()
    return challenge


async def rule_parts_challenge(
    db: AsyncSession, challenge_id: str, upheld: bool, note: str | None, user_id: str
) -> PartsChallenge:
    """Head judge ruling: the losing side is disqualified for that round.

    Upheld → the challenged team is DQ'd; rejected (wrong or spurious) → the
    challenger is. The DQ is written onto the team's score row of the match,
    which re-runs the head-to-head outcome.
    """
    challenge = await db.get(PartsChallenge, challenge_id)
    if not challenge:
        raise NotFoundError("Parts challenge not found")
    await ensure_writable(db, event_id=challenge.event_id)
    if challenge.upheld is not None:
        raise ConflictError("The challenge has already been ruled on")
    challenge.upheld = upheld
    challenge.ruling_note = note
    challenge.decided_by = user_id
    challenge.decided_at = datetime.now(UTC)
    loser = challenge.challenged_team_id if upheld else challenge.challenger_team_id
    if challenge.scheduled_match_id:
        for match in await rules_service.head_to_head_matches(db, challenge.scheduled_match_id):
            if match.team_id == loser and not match.is_disqualified:
                await score_service.update_match(
                    db,
                    match.id,
                    changed_by=user_id,
                    correction_reason=f"Parts challenge {'upheld' if upheld else 'rejected'}",
                    is_disqualified=True,
                )
    await db.flush()
    return challenge


# ── Scouting ──────────────────────────────────────────────────────────────────


async def _scope(db: AsyncSession, user) -> set[str] | None:
    """None for organizers (see everything), else the caller's own team ids."""
    if await has_elevated_access(db, user, ORGANIZER):
        return None
    return await own_team_ids(db, user)


async def list_external_teams(db: AsyncSession, season_id: str) -> list[ExternalTeam]:
    result = await db.execute(
        select(ExternalTeam).where(ExternalTeam.season_id == season_id).order_by(ExternalTeam.name)
    )
    return list(result.scalars())


async def create_external_team(db: AsyncSession, data: dict[str, Any], user) -> ExternalTeam:
    if not await db.get(Season, data["season_id"]):
        raise NotFoundError("Season not found")
    await ensure_writable(db, season_id=data["season_id"])
    team = ExternalTeam(**data, created_by=user.id)
    db.add(team)
    await db.flush()
    return team


async def update_external_team(
    db: AsyncSession, external_team_id: str, data: dict[str, Any], user
) -> ExternalTeam:
    team = await db.get(ExternalTeam, external_team_id)
    if not team:
        raise NotFoundError("External team not found")
    await ensure_writable(db, season_id=team.season_id)
    if team.created_by != user.id and not await has_elevated_access(db, user, ORGANIZER):
        raise ForbiddenError("Only organizers or the creator may edit this team")
    for key, value in data.items():
        setattr(team, key, value)
    await db.flush()
    return team


async def delete_external_team(db: AsyncSession, external_team_id: str) -> None:
    team = await db.get(ExternalTeam, external_team_id)
    if not team:
        raise NotFoundError("External team not found")
    await ensure_writable(db, season_id=team.season_id)
    await db.delete(team)
    await db.flush()


async def _event_and_external(db: AsyncSession, event_id: str, external_team_id: str) -> Event:
    event = await db.get(Event, event_id)
    if not event:
        raise NotFoundError("Event not found")
    external = await db.get(ExternalTeam, external_team_id)
    if not external or external.season_id != event.season_id:
        raise ValidationError("External team does not belong to this event's season")
    await ensure_writable(db, event_id=event_id)
    return event


async def _owner_for_write(db: AsyncSession, user, owner_team_id: str | None) -> str | None:
    """Mentors write notes for one of their own teams; organizers may write unowned notes."""
    scope = await _scope(db, user)
    if scope is None:
        return owner_team_id
    if not owner_team_id:
        if len(scope) == 1:
            return next(iter(scope))
        raise ValidationError("owner_team_id is required")
    if owner_team_id not in scope:
        raise ForbiddenError("You may only write scouting data for your own team")
    return owner_team_id


def _visible(query, model, scope: set[str] | None):
    if scope is None:
        return query
    return query.where(model.owner_team_id.in_(scope))


async def list_notes(
    db: AsyncSession, event_id: str, user, external_team_id: str | None = None
) -> list[ScoutingNote]:
    query = select(ScoutingNote).where(ScoutingNote.event_id == event_id)
    if external_team_id:
        query = query.where(ScoutingNote.external_team_id == external_team_id)
    query = _visible(query, ScoutingNote, await _scope(db, user))
    return list((await db.execute(query.order_by(ScoutingNote.created_at))).scalars())


async def create_note(db: AsyncSession, event_id: str, data: dict[str, Any], user) -> ScoutingNote:
    await _event_and_external(db, event_id, data["external_team_id"])
    data["owner_team_id"] = await _owner_for_write(db, user, data.get("owner_team_id"))
    note = ScoutingNote(event_id=event_id, author_id=user.id, **data)
    db.add(note)
    await db.flush()
    return note


async def _editable(db: AsyncSession, model, row_id: str, user):
    row = await db.get(model, row_id)
    if not row:
        raise NotFoundError("Scouting entry not found")
    scope = await _scope(db, user)
    if scope is not None and row.owner_team_id not in scope:
        # Not found rather than forbidden: other teams' scouting is not disclosed.
        raise NotFoundError("Scouting entry not found")
    await ensure_writable(db, event_id=row.event_id)
    return row


async def update_note(db: AsyncSession, note_id: str, data: dict[str, Any], user) -> ScoutingNote:
    note = await _editable(db, ScoutingNote, note_id, user)
    for key, value in data.items():
        setattr(note, key, value)
    await db.flush()
    await db.refresh(note)
    return note


async def delete_note(db: AsyncSession, note_id: str, user) -> None:
    await db.delete(await _editable(db, ScoutingNote, note_id, user))
    await db.flush()


async def list_observations(
    db: AsyncSession, event_id: str, user, external_team_id: str | None = None
) -> list[ScoutingObservation]:
    query = select(ScoutingObservation).where(ScoutingObservation.event_id == event_id)
    if external_team_id:
        query = query.where(ScoutingObservation.external_team_id == external_team_id)
    query = _visible(query, ScoutingObservation, await _scope(db, user))
    return list((await db.execute(query.order_by(ScoutingObservation.created_at))).scalars())


async def create_observation(
    db: AsyncSession, event_id: str, data: dict[str, Any], user
) -> ScoutingObservation:
    await _event_and_external(db, event_id, data["external_team_id"])
    data["owner_team_id"] = await _owner_for_write(db, user, data.get("owner_team_id"))
    row = ScoutingObservation(event_id=event_id, author_id=user.id, **data)
    db.add(row)
    await db.flush()
    return row


async def delete_observation(db: AsyncSession, observation_id: str, user) -> None:
    await db.delete(await _editable(db, ScoutingObservation, observation_id, user))
    await db.flush()


async def opponent_ranking(db: AsyncSession, event_id: str, user) -> list[dict[str, Any]]:
    """Our teams (official seeding) and observed external teams, in one table.

    External teams are rated like a seed score: the average of their best two
    observed seeding runs (all observations if none are seeding runs). Only the
    observations the caller may see are used.
    """
    event = await db.get(Event, event_id)
    if not event:
        raise NotFoundError("Event not found")
    entries: list[dict[str, Any]] = []

    ranking_rows = await db.execute(
        select(Ranking, Team)
        .join(Team, Team.id == Ranking.team_id)
        .where(Ranking.event_id == event_id)
    )
    best: dict[str, tuple[Ranking, Team]] = {}
    for ranking, team in ranking_rows.all():
        current = best.get(team.id)
        if current is None or ranking.seed_score > current[0].seed_score:
            best[team.id] = (ranking, team)
    for ranking, team in best.values():
        entries.append(
            {
                "kind": "internal",
                "team_id": team.id,
                "team_name": team.name,
                "team_number": team.team_number,
                "country": team.country,
                "seed_score": round(ranking.seed_score, 2),
                "best_score": round(ranking.best_score, 2),
                "runs": ranking.rounds_played,
                "official_rank": ranking.rank,
            }
        )

    observations = await list_observations(db, event_id, user)
    by_team: dict[str, list[ScoutingObservation]] = {}
    for obs in observations:
        by_team.setdefault(obs.external_team_id, []).append(obs)
    externals = {t.id: t for t in await list_external_teams(db, event.season_id)}
    for external_id, rows in by_team.items():
        external = externals.get(external_id)
        if not external:
            continue
        seeding = [max(o.score, 0.0) for o in rows if o.phase == "seeding"]
        scores = seeding or [max(o.score, 0.0) for o in rows]
        entries.append(
            {
                "kind": "external",
                "team_id": external.id,
                "team_name": external.name,
                "team_number": external.number,
                "country": external.country,
                "seed_score": round(score_service.compute_seed_score(scores), 2),
                "best_score": round(max(scores), 2),
                "runs": len(rows),
                "official_rank": None,
            }
        )

    entries.sort(key=lambda e: (-e["seed_score"], -e["best_score"], e["team_name"]))
    for rank, entry in enumerate(entries, start=1):
        entry["rank"] = rank
    return entries


async def scouting_report(db: AsyncSession, event_id: str, user) -> dict[str, Any]:
    """Everything the PDF report shows, already scoped to the caller."""
    event = await db.get(Event, event_id)
    if not event:
        raise NotFoundError("Event not found")
    externals = await list_external_teams(db, event.season_id)
    notes = await list_notes(db, event_id, user)
    observations = await list_observations(db, event_id, user)
    return {
        "event": event,
        "ranking": await opponent_ranking(db, event_id, user),
        "teams": externals,
        "notes": notes,
        "observations": observations,
    }


# ── Qualification ─────────────────────────────────────────────────────────────


async def is_qualified(db: AsyncSession, season_id: str, team_id: str, level_id: str) -> bool:
    result = await db.execute(
        select(TeamQualification.id).where(
            TeamQualification.season_id == season_id,
            TeamQualification.team_id == team_id,
            TeamQualification.level_id == level_id,
        )
    )
    return result.first() is not None


async def assert_qualified(
    db: AsyncSession, season_id: str, team_id: str, level_id: str | None
) -> None:
    """A level that qualifies from another (GCER <- ECER) admits qualified teams only.

    Called on top of the registration's other checks (archive guard, the
    season's registration window and draft visibility), never instead of them.
    """
    if not level_id:
        return
    level = await db.get(CompetitionLevel, level_id)
    if level and level.qualifies_from_level_id:
        if not await is_qualified(db, season_id, team_id, level_id):
            raise ValidationError(f"Team has not qualified for {level.name} in this season")


async def list_qualifications(
    db: AsyncSession, season_id: str, level_id: str | None = None
) -> list[dict[str, Any]]:
    query = (
        select(TeamQualification, Team.name)
        .join(Team, Team.id == TeamQualification.team_id)
        .where(TeamQualification.season_id == season_id)
        .order_by(Team.name)
    )
    if level_id:
        query = query.where(TeamQualification.level_id == level_id)
    out = []
    for qualification, team_name in (await db.execute(query)).all():
        out.append(
            {
                "id": qualification.id,
                "season_id": qualification.season_id,
                "team_id": qualification.team_id,
                "team_name": team_name,
                "level_id": qualification.level_id,
                "from_level_id": qualification.from_level_id,
                "source_event_id": qualification.source_event_id,
                "note": qualification.note,
                "qualified_by": qualification.qualified_by,
                "created_at": qualification.created_at,
            }
        )
    return out


async def qualify_teams(
    db: AsyncSession,
    level_id: str,
    season_id: str,
    team_ids: list[str],
    note: str | None,
    source_event_id: str | None,
    user_id: str,
) -> list[dict[str, Any]]:
    """Mark teams as qualified for `level_id` (manual admin decision, with a note)."""
    level = await db.get(CompetitionLevel, level_id)
    if not level:
        raise NotFoundError("Competition level not found")
    if not await db.get(Season, season_id):
        raise NotFoundError("Season not found")
    await ensure_writable(db, season_id=season_id)
    if source_event_id:
        source_event = await db.get(Event, source_event_id)
        if not source_event or source_event.season_id != season_id:
            raise ValidationError("Source event does not belong to this season")
    teams = await _team_names(db, set(team_ids))
    missing = set(team_ids) - set(teams)
    if missing:
        raise NotFoundError("Team not found")
    for team_id in dict.fromkeys(team_ids):
        if await is_qualified(db, season_id, team_id, level_id):
            continue
        db.add(
            TeamQualification(
                season_id=season_id,
                team_id=team_id,
                level_id=level_id,
                from_level_id=level.qualifies_from_level_id,
                source_event_id=source_event_id,
                note=note,
                qualified_by=user_id,
            )
        )
    await db.flush()
    return [q for q in await list_qualifications(db, season_id, level_id) if q["team_id"] in teams]


async def revoke_qualification(db: AsyncSession, qualification_id: str) -> None:
    row = await db.get(TeamQualification, qualification_id)
    if not row:
        raise NotFoundError("Qualification not found")
    await ensure_writable(db, season_id=row.season_id)
    registered = await db.execute(
        select(EventRegistration.id)
        .join(Event, Event.id == EventRegistration.event_id)
        .where(
            Event.season_id == row.season_id,
            EventRegistration.team_id == row.team_id,
            EventRegistration.competition_level_id == row.level_id,
        )
    )
    if registered.first():
        raise ConflictError("The team is already registered for this level; remove it first")
    await db.delete(row)
    await db.flush()


async def qualification_status(
    db: AsyncSession, season_id: str, level_id: str
) -> list[dict[str, Any]]:
    """Candidates for `level_id`: the teams that took part in the source level.

    A team counts as a candidate when it was registered for an event of the
    season at the level this one qualifies from (any level if none is set).
    """
    level = await db.get(CompetitionLevel, level_id)
    if not level:
        raise NotFoundError("Competition level not found")
    query = (
        select(Team.id, Team.name)
        .join(EventRegistration, EventRegistration.team_id == Team.id)
        .join(Event, Event.id == EventRegistration.event_id)
        .where(Event.season_id == season_id)
        .distinct()
    )
    if level.qualifies_from_level_id:
        query = query.where(EventRegistration.competition_level_id == level.qualifies_from_level_id)
    candidates = {row.id: row.name for row in (await db.execute(query)).all()}
    qualified = {q["team_id"]: q for q in await list_qualifications(db, season_id, level_id)}
    for team_id, q in qualified.items():
        candidates.setdefault(team_id, q["team_name"])
    return sorted(
        (
            {
                "team_id": team_id,
                "team_name": name,
                "qualified": team_id in qualified,
                "qualification_id": qualified[team_id]["id"] if team_id in qualified else None,
                "note": qualified[team_id]["note"] if team_id in qualified else None,
            }
            for team_id, name in candidates.items()
        ),
        key=lambda e: (not e["qualified"], e["team_name"]),
    )


async def register_qualified(
    db: AsyncSession, event_id: str, level_id: str, category: str
) -> list[EventRegistration]:
    """Register every team qualified for `level_id` that is not yet registered."""
    from modules.events import service as event_service

    event = await db.get(Event, event_id)
    if not event:
        raise NotFoundError("Event not found")
    await ensure_writable(db, event_id=event_id)
    existing = set(
        (
            await db.execute(
                select(EventRegistration.team_id).where(EventRegistration.event_id == event_id)
            )
        ).scalars()
    )
    created = []
    for q in await list_qualifications(db, event.season_id, level_id):
        if q["team_id"] in existing:
            continue
        created.append(
            await event_service.add_registration(
                db,
                event_id,
                {"team_id": q["team_id"], "competition_level_id": level_id, "category": category},
            )
        )
    return created
