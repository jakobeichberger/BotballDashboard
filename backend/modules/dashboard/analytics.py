"""Aggregations behind the performance dashboard, event statistics and the
multi-year team history.

Everything here reads; nothing writes. The seeding figures come from the
ranking cache and the overall figures from the formula engine, so a preview
shows exactly what the official ranking would show if the event ended now.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.exceptions import NotFoundError
from modules.dashboard.statistics import (
    RunSample,
    box_summary,
    detect_anomalies,
    field_points,
    mean,
)
from modules.events.models import Event, EventPhase, EventRegistration
from modules.scoring import formula_service
from modules.scoring.models import Match, Ranking
from modules.scoring.ranking import rank_descending
from modules.scoring.service import compute_match_total, get_active_schema
from modules.seasons.models import Season
from modules.teams.models import Team, TeamSeasonRegistration

logger = logging.getLogger(__name__)

PRACTICE = "practice"
#: Official runs without an event phase are seeding runs (the default phase).
DEFAULT_PHASE = "seeding"


# ── Shared lookups ────────────────────────────────────────────────────────────


async def _get_event(db: AsyncSession, event_id: str) -> Event:
    event = await db.get(Event, event_id)
    if not event:
        raise NotFoundError("Event not found")
    return event


async def _team_names(db: AsyncSession, team_ids: set[str]) -> dict[str, dict[str, Any]]:
    if not team_ids:
        return {}
    result = await db.execute(
        select(Team.id, Team.name, Team.team_number).where(Team.id.in_(team_ids))
    )
    return {r.id: {"name": r.name, "number": r.team_number} for r in result}


async def _phase_types(db: AsyncSession, event_id: str) -> dict[str, tuple[str, str]]:
    result = await db.execute(
        select(EventPhase.id, EventPhase.name, EventPhase.phase_type).where(
            EventPhase.event_id == event_id
        )
    )
    return {r.id: (r.name, r.phase_type) for r in result}


async def schema_fields_for_event(db: AsyncSession, event: Event) -> list[dict[str, Any]]:
    schema = await get_active_schema(db, event.season_id, None, event.id)
    return list(schema.fields) if schema else []


def _run_fields(match: Match, fallback: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The fields a run was scored with: its own snapshot, else the event schema."""
    snapshot = match.schema_snapshot or {}
    fields = snapshot.get("fields") if isinstance(snapshot, dict) else None
    return list(fields) if fields else fallback


def _phase_key(match: Match, phases: dict[str, tuple[str, str]]) -> str:
    if match.is_practice:
        return PRACTICE
    if match.event_phase_id and match.event_phase_id in phases:
        return phases[match.event_phase_id][1]
    return DEFAULT_PHASE


def _order(match: Match) -> tuple[Any, ...]:
    created = match.created_at or datetime.min
    return (created, match.round_number)


def _slope(values: list[float]) -> float | None:
    """Least-squares slope per run — positive means the team is improving."""
    n = len(values)
    if n < 2:
        return None
    mean_x = (n - 1) / 2
    mean_y = sum(values) / n
    denominator = sum((i - mean_x) ** 2 for i in range(n))
    numerator = sum((i - mean_x) * (v - mean_y) for i, v in enumerate(values))
    return round(numerator / denominator, 3) if denominator else None


async def _team_category(db: AsyncSession, event: Event, team_id: str) -> str:
    result = await db.execute(
        select(EventRegistration.category).where(
            EventRegistration.event_id == event.id, EventRegistration.team_id == team_id
        )
    )
    category = result.scalar_one_or_none()
    if category:
        return category
    result = await db.execute(
        select(TeamSeasonRegistration.category).where(
            TeamSeasonRegistration.season_id == event.season_id,
            TeamSeasonRegistration.team_id == team_id,
        )
    )
    return result.scalar_one_or_none() or "botball"


async def seeding_table(db: AsyncSession, event: Event) -> list[dict[str, Any]]:
    """Current seeding standings of an event from the ranking cache.

    Runs without a phase and runs of a phase typed "seeding" both count as
    seeding; a team's phase-less row wins over a phase row.
    """
    return (await seeding_tables(db, {event.id}))[event.id]


async def seeding_tables(db: AsyncSession, event_ids: set[str]) -> dict[str, list[dict[str, Any]]]:
    """seeding_table for several events with two queries in total."""
    if not event_ids:
        return {}
    phase_rows = await db.execute(
        select(EventPhase.id, EventPhase.phase_type).where(EventPhase.event_id.in_(event_ids))
    )
    phase_types = {r.id: r.phase_type for r in phase_rows}
    result = await db.execute(select(Ranking).where(Ranking.event_id.in_(event_ids)))
    best: dict[str, dict[str, Ranking]] = {event_id: {} for event_id in event_ids}
    for row in result.scalars():
        if row.event_phase_id is not None:
            if phase_types.get(row.event_phase_id) != "seeding":
                continue
        per_event = best[row.event_id]
        current = per_event.get(row.team_id)
        if current is None or (current.event_phase_id is not None and row.event_phase_id is None):
            per_event[row.team_id] = row
    tables: dict[str, list[dict[str, Any]]] = {}
    for event_id, rows in best.items():
        by_team = sorted(rows.values(), key=lambda r: r.team_id)
        tables[event_id] = [
            {
                "team_id": row.team_id,
                "rank": rank,
                "seed_score": row.seed_score,
                "best_score": row.best_score,
                "rounds_played": row.rounds_played,
            }
            for rank, row in rank_descending(by_team, lambda r: r.seed_score)
        ]
    return tables


async def overall_table(db: AsyncSession, event_id: str, category: str) -> list[dict[str, Any]]:
    """Formula-engine ranking of one category, or [] if the formulas fail.

    A broken formula set must not take the dashboards down with it; the
    formula editor reports the problem to whoever maintains the set.
    """
    return (await overall_tables(db, event_id, {category}))[category]


async def overall_tables(
    db: AsyncSession, event_id: str, categories: set[str]
) -> dict[str, list[dict[str, Any]]]:
    """overall_table for several categories of one event, loading its inputs once.

    A failing category (broken formula set) yields [] without affecting the
    others.
    """
    try:
        data = await formula_service.load_event_inputs(db, event_id)
    except Exception:  # noqa: BLE001 - see overall_table
        logger.warning("overall ranking failed for event %s", event_id, exc_info=True)
        return {category: [] for category in categories}
    tables: dict[str, list[dict[str, Any]]] = {}
    for category in categories:
        try:
            ranked, _ = await formula_service.compute_category_ranking(
                db, event_id, category, data=data
            )
            tables[category] = [formula_service.to_ranking_entry(r) for r in ranked]
        except Exception:  # noqa: BLE001 - see overall_table
            logger.warning("overall ranking failed for event %s", event_id, exc_info=True)
            tables[category] = []
    return tables


# ── Performance dashboard ─────────────────────────────────────────────────────


async def team_performance(
    db: AsyncSession, event_id: str, team_id: str, include_practice: bool = True
) -> dict[str, Any]:
    """Everything the per-team performance dashboard shows for one event."""
    event = await _get_event(db, event_id)
    team = await db.get(Team, team_id)
    if not team:
        raise NotFoundError("Team not found")
    phases = await _phase_types(db, event.id)
    schema_fields = await schema_fields_for_event(db, event)

    result = await db.execute(select(Match).where(Match.event_id == event.id))
    all_matches = list(result.scalars().all())
    team_matches = sorted((m for m in all_matches if m.team_id == team_id), key=_order)

    runs = [
        {
            "match_id": m.id,
            "round_number": m.round_number,
            "created_at": m.created_at,
            "total_score": m.total_score,
            "is_practice": m.is_practice,
            "is_disqualified": m.is_disqualified,
            "phase": _phase_key(m, phases),
            "phase_name": phases[m.event_phase_id][0] if m.event_phase_id in phases else None,
            "notes": m.notes,
            "confirmed": m.confirmed_at is not None,
        }
        for m in team_matches
    ]

    def counted(m: Match) -> bool:
        return not m.is_disqualified and (include_practice or not m.is_practice)

    # Strengths / weaknesses: points per field, team vs field. The field average
    # is the mean of every team's own average, so a team with many practice
    # runs does not dominate the reference.
    labels = {f["key"]: f.get("label") or f["key"] for f in schema_fields if f.get("key")}
    per_team_points: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for m in all_matches:
        if not counted(m):
            continue
        fields = _run_fields(m, schema_fields)
        for spec in fields:
            if spec.get("key") and spec["key"] not in labels:
                labels[spec["key"]] = spec.get("label") or spec["key"]
        for key, pts in field_points(m.raw_scores or {}, fields).items():
            per_team_points[m.team_id][key].append(pts)

    field_rows = []
    own = per_team_points.get(team_id, {})
    for key, label in labels.items():
        team_avg = mean(own.get(key, []))
        team_means = [
            sum(values) / len(values)
            for values in (points.get(key, []) for points in per_team_points.values())
            if values
        ]
        field_avg = mean(team_means)
        field_best = round(max(team_means), 3) if team_means else None
        delta = (
            round(team_avg - field_avg, 3)
            if team_avg is not None and field_avg is not None
            else None
        )
        field_rows.append(
            {
                "key": key,
                "label": label,
                "team_avg": team_avg,
                "field_avg": field_avg,
                "field_best": field_best,
                "delta": delta,
                "share_of_best": round(team_avg / field_best, 3)
                if team_avg is not None and field_best
                else None,
            }
        )
    rated = [r for r in field_rows if r["delta"] is not None]
    strengths = [r["key"] for r in sorted(rated, key=lambda r: -r["delta"]) if r["delta"] > 0][:3]
    weaknesses = [r["key"] for r in sorted(rated, key=lambda r: r["delta"]) if r["delta"] < 0][:3]

    # Phase comparison inside this event (practice vs seeding vs DE …).
    by_phase: dict[str, list[float]] = defaultdict(list)
    for m in team_matches:
        if not m.is_disqualified:
            by_phase[_phase_key(m, phases)].append(m.total_score)
    phase_rows = [
        {"phase": phase, **(box_summary(values) or {})} for phase, values in by_phase.items()
    ]

    # Cross-event comparison within the season: prep events against the
    # tournament, ECER against GCER.
    season_rows = await _season_event_comparison(db, event.season_id, team_id)

    # "If the event ended now".
    category = await _team_category(db, event, team_id)
    seeding = await seeding_table(db, event)
    overall = await overall_table(db, event.id, category)
    preview = _preview(team_id, seeding, overall)

    official = [m.total_score for m in team_matches if not m.is_practice and not m.is_disqualified]
    practice = [m.total_score for m in team_matches if m.is_practice and not m.is_disqualified]
    return {
        "event_id": event.id,
        "event_name": event.name,
        "team_id": team.id,
        "team_name": team.name,
        "category": category,
        "include_practice": include_practice,
        "runs": runs,
        "summary": {
            "official_runs": len(official),
            "official_avg": mean(official),
            "official_best": max(official) if official else None,
            "practice_runs": len(practice),
            "practice_avg": mean(practice),
            "practice_best": max(practice) if practice else None,
            "trend_per_run": _slope([m.total_score for m in team_matches if counted(m)]),
        },
        "fields": field_rows,
        "strengths": strengths,
        "weaknesses": weaknesses,
        "phases": phase_rows,
        "season_events": season_rows,
        "ranking_preview": preview,
    }


def _preview(
    team_id: str, seeding: list[dict[str, Any]], overall: list[dict[str, Any]]
) -> dict[str, Any]:
    preview: dict[str, Any] = {
        "seeding_rank": None,
        "seeding_score": None,
        "seeding_teams": len(seeding),
        "points_to_next_rank": None,
        "overall_rank": None,
        "overall_score": None,
        "overall_teams": len(overall),
    }
    for index, row in enumerate(seeding):
        if row["team_id"] == team_id:
            preview["seeding_rank"] = row["rank"]
            preview["seeding_score"] = row["seed_score"]
            better = [r for r in seeding[:index] if r["seed_score"] > row["seed_score"]]
            if better:
                preview["points_to_next_rank"] = round(
                    better[-1]["seed_score"] - row["seed_score"], 3
                )
            break
    for entry in overall:
        if entry["team_id"] == team_id:
            preview["overall_rank"] = entry["rank"]
            preview["overall_score"] = entry["overall_score"]
            break
    return preview


async def _season_event_comparison(
    db: AsyncSession, season_id: str, team_id: str
) -> list[dict[str, Any]]:
    events = await db.execute(select(Event).where(Event.season_id == season_id))
    event_rows = {e.id: e for e in events.scalars()}
    result = await db.execute(
        select(Match.event_id, Match.total_score, Match.is_practice).where(
            Match.team_id == team_id,
            Match.season_id == season_id,
            Match.is_disqualified.is_(False),
        )
    )
    grouped: dict[str, dict[str, list[float]]] = defaultdict(
        lambda: {"practice": [], "official": []}
    )
    for row in result:
        grouped[row.event_id]["practice" if row.is_practice else "official"].append(row.total_score)
    out = []
    for event_id, values in grouped.items():
        event = event_rows.get(event_id)
        if not event:
            continue
        out.append(
            {
                "event_id": event.id,
                "event_name": event.name,
                "event_type": event.event_type,
                "starts_at": event.starts_at,
                "practice_runs": len(values["practice"]),
                "practice_avg": mean(values["practice"]),
                "official_runs": len(values["official"]),
                "official_avg": mean(values["official"]),
                "official_best": max(values["official"]) if values["official"] else None,
            }
        )
    out.sort(key=lambda r: (r["starts_at"] is None, r["starts_at"] or datetime.min))
    return out


async def performance_overview(
    db: AsyncSession, event_id: str, team_ids: set[str] | None
) -> list[dict[str, Any]]:
    """Team comparison table: every team (or only `team_ids`) of an event,
    sorted by current official average."""
    event = await _get_event(db, event_id)
    registered = await db.execute(
        select(EventRegistration.team_id).where(EventRegistration.event_id == event.id)
    )
    ids = set(registered.scalars().all())
    result = await db.execute(select(Match).where(Match.event_id == event.id))
    matches = list(result.scalars().all())
    ids |= {m.team_id for m in matches}
    if team_ids is not None:
        ids &= team_ids
    names = await _team_names(db, ids)
    seeding = {r["team_id"]: r for r in await seeding_table(db, event)}

    rows = []
    for tid in ids:
        own = sorted((m for m in matches if m.team_id == tid), key=_order)
        official = [m.total_score for m in own if not m.is_practice and not m.is_disqualified]
        practice = [m.total_score for m in own if m.is_practice and not m.is_disqualified]
        rows.append(
            {
                "team_id": tid,
                "team_name": names.get(tid, {}).get("name", tid),
                "team_number": names.get(tid, {}).get("number"),
                "official_runs": len(official),
                "official_avg": mean(official),
                "official_best": max(official) if official else None,
                "practice_runs": len(practice),
                "practice_avg": mean(practice),
                "trend_per_run": _slope([m.total_score for m in own if not m.is_disqualified]),
                "seeding_rank": seeding.get(tid, {}).get("rank"),
                "last_run_at": own[-1].created_at if own else None,
            }
        )
    rows.sort(
        key=lambda r: (
            r["official_avg"] is None,
            -(r["official_avg"] or 0),
            -(r["practice_avg"] or 0),
            r["team_name"],
        )
    )
    return rows


# ── Event statistics & anomaly detection ──────────────────────────────────────


async def event_statistics(
    db: AsyncSession, event_id: str, include_practice: bool = False
) -> dict[str, Any]:
    """Distribution, heatmap, trends and anomalies of an event's runs."""
    event = await _get_event(db, event_id)
    schema_fields = await schema_fields_for_event(db, event)
    query = select(Match).where(Match.event_id == event.id)
    if not include_practice:
        query = query.where(Match.is_practice.is_(False))
    matches = list((await db.execute(query)).scalars().all())
    names = await _team_names(db, {m.team_id for m in matches})
    valid = [m for m in matches if not m.is_disqualified]

    labels: dict[str, str] = {
        f["key"]: f.get("label") or f["key"] for f in schema_fields if f.get("key")
    }
    run_points: dict[str, dict[str, float]] = {}
    for m in matches:
        fields = _run_fields(m, schema_fields)
        for spec in fields:
            if spec.get("key") and spec["key"] not in labels:
                labels[spec["key"]] = spec.get("label") or spec["key"]
        run_points[m.id] = field_points(m.raw_scores or {}, fields)

    # Distribution per round and per field.
    by_round: dict[int, list[float]] = defaultdict(list)
    for m in valid:
        by_round[m.round_number].append(m.total_score)
    rounds = [
        {"round_number": number, **(box_summary(values) or {})}
        for number, values in sorted(by_round.items())
    ]
    fields = []
    for key, label in labels.items():
        values = [run_points[m.id].get(key, 0.0) for m in valid]
        summary = box_summary(values)
        fields.append(
            {
                "key": key,
                "label": label,
                **(summary or {"n": 0}),
                "zero_share": round(sum(1 for v in values if v == 0) / len(values), 3)
                if values
                else None,
            }
        )

    # Heatmap: average points per team and field, plus the ratio to the best
    # team in that field (0..1) so colours are comparable across fields.
    team_ids = sorted({m.team_id for m in valid}, key=lambda t: names.get(t, {}).get("name", t))
    cells: dict[str, dict[str, float | None]] = {}
    column_max: dict[str, float] = {}
    for tid in team_ids:
        own = [m for m in valid if m.team_id == tid]
        cells[tid] = {}
        for key in labels:
            avg = mean([run_points[m.id].get(key, 0.0) for m in own])
            cells[tid][key] = avg
            if avg is not None:
                column_max[key] = max(column_max.get(key, 0.0), avg)
    heatmap = {
        "fields": [{"key": k, "label": v} for k, v in labels.items()],
        "teams": [
            {
                "team_id": tid,
                "team_name": names.get(tid, {}).get("name", tid),
                "values": [
                    {
                        "key": key,
                        "avg": cells[tid][key],
                        "ratio": round((cells[tid][key] or 0.0) / column_max[key], 3)
                        if column_max.get(key)
                        else None,
                    }
                    for key in labels
                ],
            }
            for tid in team_ids
        ],
    }

    # Trend lines: field mean per round and each team's run-by-run totals.
    trend_rounds = [
        {"round_number": r["round_number"], "mean": r.get("mean"), "median": r.get("median")}
        for r in rounds
    ]
    team_series = []
    for tid in team_ids:
        own = sorted((m for m in valid if m.team_id == tid), key=_order)
        team_series.append(
            {
                "team_id": tid,
                "team_name": names.get(tid, {}).get("name", tid),
                "points": [
                    {"round_number": m.round_number, "total_score": m.total_score, "match_id": m.id}
                    for m in own
                ],
                "slope": _slope([m.total_score for m in own]),
            }
        )

    # Anomalies. Practice and official runs are judged separately — a team's
    # practice runs are no reference for its tournament runs.
    anomalies = []
    for practice_flag in (False, True):
        subset = [m for m in matches if m.is_practice is practice_flag]
        if not subset:
            continue
        samples = []
        for m in subset:
            fields_for_run = _run_fields(m, schema_fields)
            recomputed: float | None = None
            if fields_for_run and m.raw_scores:
                snapshot = m.schema_snapshot if isinstance(m.schema_snapshot, dict) else {}
                try:
                    # Same rule as the score service: the sheet total plus the
                    # end-contact bonus, 0 for a lost round.
                    recomputed = (
                        0.0
                        if m.round_lost
                        else round(
                            compute_match_total(
                                m.raw_scores, fields_for_run, snapshot.get("definition")
                            )
                            + float(m.bonus_score or 0.0),
                            2,
                        )
                    )
                except Exception:  # noqa: BLE001 - range problems are reported per field
                    recomputed = None
            samples.append(
                RunSample(
                    match_id=m.id,
                    team_id=m.team_id,
                    total=float(m.total_score or 0.0),
                    order=_order(m),
                    is_disqualified=m.is_disqualified,
                    raw_scores=m.raw_scores or {},
                    schema_fields=fields_for_run,
                    recomputed_total=None if m.is_disqualified else recomputed,
                )
            )
        by_id = {m.id: m for m in subset}
        for match_id, findings in detect_anomalies(samples).items():
            m = by_id[match_id]
            anomalies.append(
                {
                    "match_id": m.id,
                    "team_id": m.team_id,
                    "team_name": names.get(m.team_id, {}).get("name", m.team_id),
                    "round_number": m.round_number,
                    "total_score": m.total_score,
                    "is_practice": m.is_practice,
                    "scheduled_match_id": m.scheduled_match_id,
                    "confirmed": m.confirmed_at is not None,
                    "created_at": m.created_at,
                    "severity": "error"
                    if any(f.severity == "error" for f in findings)
                    else "warning",
                    "reasons": [
                        {
                            "kind": f.kind,
                            "message": f.message,
                            "severity": f.severity,
                            "score": f.score,
                        }
                        for f in findings
                    ],
                }
            )
    anomalies.sort(key=lambda a: (a["severity"] != "error", a["team_name"], a["round_number"]))

    totals = [m.total_score for m in valid]
    return {
        "event_id": event.id,
        "event_name": event.name,
        "include_practice": include_practice,
        "overview": {
            "runs": len(matches),
            "disqualified": len(matches) - len(valid),
            "teams": len(team_ids),
            "unconfirmed": sum(1 for m in matches if m.confirmed_at is None),
            "total": box_summary(totals),
        },
        "rounds": rounds,
        "fields": fields,
        "heatmap": heatmap,
        "trend": {"rounds": trend_rounds, "teams": team_series},
        "anomalies": anomalies,
    }


# ── Multi-year history ────────────────────────────────────────────────────────


async def team_history(
    db: AsyncSession, team_id: str, include_practice: bool = False
) -> list[dict[str, Any]]:
    """One row per event the team took part in, oldest first."""
    team = await db.get(Team, team_id)
    if not team:
        raise NotFoundError("Team not found")
    return await _history_rows(db, {team_id}, include_practice)


async def all_teams_history(db: AsyncSession) -> list[dict[str, Any]]:
    """Official results of every team at every event (multi-year export)."""
    return await _history_rows(db, None, include_practice=False)


async def _history_rows(
    db: AsyncSession, team_ids: set[str] | None, include_practice: bool
) -> list[dict[str, Any]]:
    registrations = select(EventRegistration, Event, Season).join(
        Event, Event.id == EventRegistration.event_id
    )
    registrations = registrations.join(Season, Season.id == Event.season_id)
    if team_ids is not None:
        registrations = registrations.where(EventRegistration.team_id.in_(team_ids))
    reg_rows = (await db.execute(registrations)).all()

    # Teams that competed without an event registration (older data, or runs
    # entered before registering) still belong in the history.
    match_query = select(Match.team_id, Match.event_id).distinct()
    if team_ids is not None:
        match_query = match_query.where(Match.team_id.in_(team_ids))
    pairs: dict[tuple[str, str], str | None] = {
        (r.team_id, r.event_id): None for r in await db.execute(match_query)
    }
    for reg, _, _ in reg_rows:
        pairs[(reg.team_id, reg.event_id)] = reg.category
    if not pairs:
        return []

    event_ids = {event_id for _, event_id in pairs}
    events = {
        e.id: e for e in (await db.execute(select(Event).where(Event.id.in_(event_ids)))).scalars()
    }
    season_ids = {e.season_id for e in events.values()}
    seasons = {
        s.id: s
        for s in (await db.execute(select(Season).where(Season.id.in_(season_ids)))).scalars()
    }
    season_categories = {
        (r.team_id, r.season_id): r.category
        for r in (
            await db.execute(
                select(TeamSeasonRegistration).where(
                    TeamSeasonRegistration.season_id.in_(season_ids)
                )
            )
        ).scalars()
    }
    names = await _team_names(db, {team_id for team_id, _ in pairs})

    stats_query = select(Match.team_id, Match.event_id, Match.total_score, Match.is_practice).where(
        Match.event_id.in_(event_ids), Match.is_disqualified.is_(False)
    )
    if team_ids is not None:
        stats_query = stats_query.where(Match.team_id.in_(team_ids))
    runs: dict[tuple[str, str], dict[str, list[float]]] = defaultdict(
        lambda: {"official": [], "practice": []}
    )
    for stat in await db.execute(stats_query):
        runs[(stat.team_id, stat.event_id)]["practice" if stat.is_practice else "official"].append(
            stat.total_score
        )

    # Event registration first, then the season registration.
    categories = {
        (tid, event_id): reg_category
        or season_categories.get((tid, events[event_id].season_id))
        or "botball"
        for (tid, event_id), reg_category in pairs.items()
        if event_id in events
    }
    # Seeding tables of all events in one go; formula inputs once per event
    # (not once per event and category, and not once per team).
    seeding_by_event = {
        event_id: {r["team_id"]: r for r in table}
        for event_id, table in (await seeding_tables(db, set(events))).items()
    }
    wanted: dict[str, set[str]] = defaultdict(set)
    for (_, event_id), category in categories.items():
        wanted[event_id].add(category)
    overall_by_event = {
        event_id: await overall_tables(db, event_id, event_categories)
        for event_id, event_categories in wanted.items()
    }
    rows = []
    for (tid, event_id), category in categories.items():
        event = events[event_id]
        season = seasons[event.season_id]
        seed = seeding_by_event[event_id].get(tid)
        overall_rows = overall_by_event[event_id][category]
        overall = next((r for r in overall_rows if r["team_id"] == tid), None)
        values = runs.get((tid, event_id), {"official": [], "practice": []})
        entry: dict[str, Any] = {
            "team_id": tid,
            "team_name": names.get(tid, {}).get("name", tid),
            "team_number": names.get(tid, {}).get("number"),
            "season_id": season.id,
            "season_name": season.name,
            "season_year": season.year,
            "event_id": event.id,
            "event_name": event.name,
            "event_type": event.event_type,
            "starts_at": event.starts_at,
            "category": category,
            "seeding_rank": seed["rank"] if seed else None,
            "seeding_score": seed["seed_score"] if seed else None,
            "seeding_teams": len(seeding_by_event[event_id]),
            "best_score": max(values["official"]) if values["official"] else None,
            "official_runs": len(values["official"]),
            "official_avg": mean(values["official"]),
            "overall_rank": overall["rank"] if overall else None,
            "overall_score": overall["overall_score"] if overall else None,
            "overall_teams": len(overall_rows),
            "de_score": overall.get("de_score") if overall else None,
            "doc_score": overall.get("doc_score") if overall else None,
            "paper_score": overall.get("paper_score") if overall else None,
        }
        if include_practice:
            entry["practice_runs"] = len(values["practice"])
            entry["practice_avg"] = mean(values["practice"])
        rows.append(entry)
    rows.sort(
        key=lambda r: (
            r["season_year"],
            r["starts_at"] is None,
            r["starts_at"] or datetime.min,
            r["event_name"],
            r["team_name"],
        )
    )
    return rows
