"""Season rule set lookup and the head-to-head special rules.

Kept free of imports from ``modules.scoring.service`` so the score service can
call into it without a cycle.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.events.models import EventPhase, MatchParticipant, ScheduledMatch
from modules.scoring import tiebreak
from modules.scoring.extras_models import ScoringRuleSet
from modules.scoring.models import Match


@dataclass
class Rules:
    tiebreakers: list[dict[str, Any]] = field(default_factory=list)
    finals_replay: bool = False
    end_contact_bonus_percent: float = 25.0
    referee_checklist: list[dict[str, Any]] = field(default_factory=list)


async def get_rules(db: AsyncSession, season_id: str) -> Rules:
    result = await db.execute(select(ScoringRuleSet).where(ScoringRuleSet.season_id == season_id))
    row = result.scalar_one_or_none()
    if not row:
        return Rules()
    return Rules(
        tiebreakers=list(row.tiebreakers or []),
        finals_replay=bool(row.finals_replay),
        end_contact_bonus_percent=float(row.end_contact_bonus_percent),
        referee_checklist=list(row.referee_checklist or []),
    )


def snapshot_definition(match: Match) -> dict | None:
    """The structured definition a match was scored with (flat → sections)."""
    from modules.scoring import sheet

    snapshot = match.schema_snapshot or {}
    return sheet.normalize(snapshot.get("fields"), snapshot.get("definition"))


def apply_round_rules(match: Match) -> None:
    """total = 0 when the round is lost, else sheet score + contact bonus."""
    match.total_score = 0.0 if match.round_lost else round(match.sheet_score + match.bonus_score, 2)


def contestant(match: Match, criteria: list[dict[str, Any]]) -> tiebreak.Contestant:
    return tiebreak.Contestant(
        team_id=match.team_id,
        total=float(match.total_score or 0.0),
        disqualified=bool(match.is_disqualified),
        round_lost=bool(match.round_lost),
        round_lost_reason=match.round_lost_reason,
        values=tiebreak.match_values(
            criteria, match.raw_scores, match.tiebreak_values, snapshot_definition(match)
        ),
    )


async def head_to_head_matches(db: AsyncSession, scheduled_match_id: str) -> list[Match]:
    """The official score rows of one head-to-head match, latest per team."""
    result = await db.execute(
        select(Match)
        .where(Match.scheduled_match_id == scheduled_match_id, Match.is_practice.is_(False))
        .order_by(Match.created_at)
    )
    latest: dict[str, Match] = {}
    for match in result.scalars():
        latest[match.team_id] = match
    return list(latest.values())


async def apply_head_to_head(db: AsyncSession, scheduled_match_id: str, season_id: str) -> dict:
    """Recompute the 25 % contact bonus and the outcome of one head-to-head match.

    Returns the outcome (see tiebreak.Outcome) and writes each participant's
    score onto the schedule. Matches with only one team (seeding) are left
    alone.

    The result itself goes where the phase keeps it:

    * elimination phases (DE, final): a decided outcome is recorded through
      events.service.record_match_result — the one place that advances the
      bracket, corrects an earlier result and writes the DE placements. A tie
      that nothing breaks (replay) leaves an open match open.
    * other head-to-head phases (double seeding): win / loss / replay on the
      participants.
    """
    matches = await head_to_head_matches(db, scheduled_match_id)
    rules = await get_rules(db, season_id)
    if len(matches) != 2:
        for match in matches:
            if match.bonus_score:
                match.bonus_score = 0.0
                apply_round_rules(match)
        return {"winner": None, "reason": "incomplete", "decided_by": None, "replay": False}

    a, b = matches
    for own, other in ((a, b), (b, a)):
        own.bonus_score = (
            tiebreak.end_contact_bonus(other.sheet_score, rules.end_contact_bonus_percent)
            if other.end_contact and not other.round_lost
            else 0.0
        )
    for match in matches:
        apply_round_rules(match)

    scheduled = await db.get(ScheduledMatch, scheduled_match_id)
    phase = await db.get(EventPhase, scheduled.phase_id) if scheduled else None
    is_final = bool(scheduled and scheduled.bracket == "final") or bool(
        phase and phase.phase_type == "final"
    )
    replayed = any(bool((m.tiebreak_values or {}).get(tiebreak.REPLAYED_KEY)) for m in matches)
    outcome = tiebreak.decide_head_to_head(
        contestant(a, rules.tiebreakers),
        contestant(b, rules.tiebreakers),
        rules.tiebreakers,
        is_final=is_final,
        finals_replay=rules.finals_replay,
        replayed=replayed,
    )

    participants = list(
        (
            await db.execute(
                select(MatchParticipant).where(
                    MatchParticipant.scheduled_match_id == scheduled_match_id
                )
            )
        ).scalars()
    )
    totals = {m.team_id: m.total_score for m in matches}
    by_team = {p.team_id: p for p in participants if p.team_id in totals}
    for team_id, participant in by_team.items():
        participant.score = totals[team_id]
    await db.flush()

    from modules.events import service as event_service

    elimination = bool(phase and phase.phase_type in event_service.ELIMINATION_PHASES)
    if not elimination:
        for team_id, participant in by_team.items():
            if outcome.replay:
                participant.result = "replay"
            else:
                participant.result = "win" if team_id == outcome.winner else "loss"
        await db.flush()
    elif scheduled and scheduled.status != "cancelled" and len(by_team) == 2:
        current = next((p.team_id for p in by_team.values() if p.result == "win"), None)
        if outcome.winner and (scheduled.status != "completed" or current != outcome.winner):
            await event_service.record_match_result(
                db,
                scheduled.event_id,
                scheduled_match_id,
                {"winner_team_id": outcome.winner, "scores": totals},
            )
        elif outcome.replay and scheduled.status != "completed":
            for participant in by_team.values():
                participant.result = "replay"
            await db.flush()
    return outcome.as_dict()
