"""Season clone and JSON export.

Cloning copies a season's *configuration* – module flags, phases, deadlines,
events (as empty drafts), scoring schemas, formulas and bracket weights – into a
new draft season, shifting every date by the difference in years. Results,
registrations and other tournament data are never copied.

The export is the opposite: a complete, self-contained JSON snapshot of
everything that happened in a season, for archiving outside the application.
"""

import re
from datetime import UTC, date, datetime
from typing import Any, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.exceptions import NotFoundError
from modules.seasons.lifecycle import DRAFT
from modules.seasons.models import Season, SeasonEvent, SeasonPhase

EXPORT_FORMAT_VERSION = 1

_D = TypeVar("_D", date, datetime)

# Season columns carried over to a clone; everything else is either identity,
# lifecycle state or bookkeeping.
_CLONED_SEASON_FIELDS = (
    "game_theme",
    "notes",
    "use_seeding",
    "use_double_elimination",
    "use_paper_scoring",
    "use_documentation_scoring",
    "use_aerial",
)
_SHIFTED_SEASON_DATES = (
    "registration_open",
    "registration_close",
    "event_start",
    "event_end",
    "paper_submission_deadline",
    "print_submission_deadline",
)
_CLONED_EVENT_FIELDS = (
    "name",
    "event_type",
    "timezone",
    "venue",
    "active_modules",
    "public_scoreboard",
    "public_schedule",
    "public_results",
    "public_announcements",
    "table_count",
    "notes",
)


def shift_years(value: _D | None, years: int) -> _D | None:
    """Move a date by whole years; 29 February becomes 28 February if needed."""
    if value is None or years == 0:
        return value
    try:
        return value.replace(year=value.year + years)
    except ValueError:
        return value.replace(year=value.year + years, day=28)


def _shift_text(text: str, old_year: int, new_year: int) -> str:
    """Replace the source year in names/slugs ("ECER 2025" → "ECER 2026")."""
    if old_year == new_year:
        return text
    return re.sub(rf"(?<!\d){old_year}(?!\d)", str(new_year), text)


async def _unique_slug(db: AsyncSession, base: str) -> str:
    from modules.events.models import Event

    base = base[:110]
    candidate, counter = base, 2
    while (await db.execute(select(Event.id).where(Event.slug == candidate))).first():
        candidate = f"{base}-{counter}"
        counter += 1
    return candidate


async def clone_season(db: AsyncSession, source_id: str, name: str, year: int) -> Season:
    from modules.events.models import Event, EventPhase
    from modules.scoring.formula_models import ScoringBracketWeight, ScoringFormula
    from modules.scoring.models import ScoringSchema

    result = await db.execute(
        select(Season).where(Season.id == source_id).options(selectinload(Season.phases))
    )
    source = result.scalar_one_or_none()
    if source is None:
        raise NotFoundError("Season not found")
    delta = year - source.year

    clone = Season(
        name=name,
        year=year,
        is_active=False,
        status=DRAFT,
        active_categories=list(source.active_categories or ["botball"]),
        **{field: getattr(source, field) for field in _CLONED_SEASON_FIELDS},
        **{field: shift_years(getattr(source, field), delta) for field in _SHIFTED_SEASON_DATES},
    )
    db.add(clone)
    await db.flush()

    for phase in source.phases:
        db.add(
            SeasonPhase(
                season_id=clone.id,
                name=phase.name,
                phase_type=phase.phase_type,
                sort_order=phase.sort_order,
                rounds=phase.rounds,
                is_active=False,
                start_date=shift_years(phase.start_date, delta),
                end_date=shift_years(phase.end_date, delta),
            )
        )

    deadlines = await db.execute(select(SeasonEvent).where(SeasonEvent.season_id == source.id))
    for deadline in deadlines.scalars().all():
        db.add(
            SeasonEvent(
                season_id=clone.id,
                title=deadline.title,
                event_type=deadline.event_type,
                event_date=shift_years(deadline.event_date, delta),
                description=deadline.description,
            )
        )

    # Events become empty drafts with the same structure (phases, modules,
    # public flags); registrations, schedules and results stay behind.
    event_map: dict[str, str] = {}
    events = await db.execute(
        select(Event).where(Event.season_id == source.id).options(selectinload(Event.phases))
    )
    for event in events.scalars().all():
        copied = Event(
            season_id=clone.id,
            status=DRAFT,
            slug=await _unique_slug(db, _shift_text(event.slug, source.year, year)),
            starts_at=shift_years(event.starts_at, delta),
            ends_at=shift_years(event.ends_at, delta),
            **{field: getattr(event, field) for field in _CLONED_EVENT_FIELDS},
        )
        copied.name = _shift_text(copied.name, source.year, year)
        copied.active_modules = list(event.active_modules or [])
        db.add(copied)
        await db.flush()
        event_map[event.id] = copied.id
        for event_phase in event.phases:
            db.add(
                EventPhase(
                    event_id=copied.id,
                    name=event_phase.name,
                    phase_type=event_phase.phase_type,
                    sort_order=event_phase.sort_order,
                    status=DRAFT,
                    rounds=event_phase.rounds,
                    starts_at=shift_years(event_phase.starts_at, delta),
                    ends_at=shift_years(event_phase.ends_at, delta),
                    settings=dict(event_phase.settings or {}),
                )
            )

    # Only the active version of each scoring schema scope is carried over; it
    # starts again at version 1 in the new season. The competition level link
    # (competition levels are global) is kept as is.
    schemas = await db.execute(
        select(ScoringSchema).where(
            ScoringSchema.season_id == source.id, ScoringSchema.is_active.is_(True)
        )
    )
    for schema in schemas.scalars().all():
        if schema.event_id is not None and schema.event_id not in event_map:
            continue
        db.add(
            ScoringSchema(
                season_id=clone.id,
                event_id=event_map.get(schema.event_id) if schema.event_id else None,
                competition_level_id=schema.competition_level_id,
                fields=list(schema.fields or []),
                version=1,
                is_active=True,
            )
        )

    formulas = await db.execute(select(ScoringFormula).where(ScoringFormula.season_id == source.id))
    for formula in formulas.scalars().all():
        db.add(
            ScoringFormula(
                season_id=clone.id,
                category=formula.category,
                key=formula.key,
                expression=formula.expression,
                label=formula.label,
                description=formula.description,
                sort_order=formula.sort_order,
                is_active=formula.is_active,
            )
        )

    weights = await db.execute(
        select(ScoringBracketWeight).where(ScoringBracketWeight.season_id == source.id)
    )
    for weight in weights.scalars().all():
        db.add(
            ScoringBracketWeight(
                season_id=clone.id,
                category=weight.category,
                bracket=weight.bracket,
                weight=weight.weight,
            )
        )

    await db.flush()
    await db.refresh(clone, ["phases"])
    return clone


# ── Export ────────────────────────────────────────────────────────────────────


def _row(obj: Any, exclude: tuple[str, ...] = ()) -> dict[str, Any]:
    return {
        attr.key: getattr(obj, attr.key)
        for attr in obj.__mapper__.column_attrs
        if attr.key not in exclude
    }


async def _rows(db: AsyncSession, query, exclude: tuple[str, ...] = ()) -> list[dict[str, Any]]:
    result = await db.execute(query)
    return [_row(item, exclude) for item in result.scalars().all()]


async def export_season(db: AsyncSession, season_id: str) -> dict[str, Any]:
    from modules.events.models import (
        Event,
        EventPhase,
        EventRegistration,
        MatchParticipant,
        ScheduledMatch,
    )
    from modules.paper_review.models import Paper, PaperStatusHistory
    from modules.printing.models import PrintJob
    from modules.scoring.competition_models import AerialResult, DEResult, DocumentationScore
    from modules.scoring.formula_models import ScoringBracketWeight, ScoringFormula
    from modules.scoring.models import Match, Ranking, ScoreRevision, ScoringSchema
    from modules.seasons.service import get_season
    from modules.teams.models import Team, TeamSeasonRegistration

    season = await get_season(db, season_id)
    event_ids = select(Event.id).where(Event.season_id == season_id)
    paper_ids = select(Paper.id).where(Paper.season_id == season_id)
    match_ids = select(ScheduledMatch.id).where(ScheduledMatch.event_id.in_(event_ids))

    team_season_registrations = await _rows(
        db, select(TeamSeasonRegistration).where(TeamSeasonRegistration.season_id == season_id)
    )
    event_registrations = await _rows(
        db, select(EventRegistration).where(EventRegistration.event_id.in_(event_ids))
    )
    matches = await _rows(db, select(Match).where(Match.season_id == season_id))
    team_ids = {row["team_id"] for row in team_season_registrations + event_registrations + matches}
    # Team master data only – member names and e-mail addresses are personal
    # data that does not belong in an archive file.
    teams = await _rows(
        db,
        select(Team).where(Team.id.in_(team_ids)).order_by(Team.name),
        exclude=("notes",),
    )

    return {
        "format_version": EXPORT_FORMAT_VERSION,
        "exported_at": datetime.now(UTC),
        "season": _row(season),
        "season_phases": [_row(phase) for phase in season.phases],
        "deadlines": await _rows(db, select(SeasonEvent).where(SeasonEvent.season_id == season_id)),
        "events": await _rows(db, select(Event).where(Event.season_id == season_id)),
        "event_phases": await _rows(
            db, select(EventPhase).where(EventPhase.event_id.in_(event_ids))
        ),
        "teams": teams,
        "team_season_registrations": team_season_registrations,
        "event_registrations": event_registrations,
        "scheduled_matches": await _rows(
            db, select(ScheduledMatch).where(ScheduledMatch.event_id.in_(event_ids))
        ),
        "match_participants": await _rows(
            db, select(MatchParticipant).where(MatchParticipant.scheduled_match_id.in_(match_ids))
        ),
        "matches": matches,
        "score_revisions": await _rows(
            db, select(ScoreRevision).where(ScoreRevision.event_id.in_(event_ids))
        ),
        "rankings": await _rows(db, select(Ranking).where(Ranking.season_id == season_id)),
        "de_results": await _rows(db, select(DEResult).where(DEResult.season_id == season_id)),
        "aerial_results": await _rows(
            db, select(AerialResult).where(AerialResult.season_id == season_id)
        ),
        "documentation_scores": await _rows(
            db, select(DocumentationScore).where(DocumentationScore.season_id == season_id)
        ),
        "scoring_schemas": await _rows(
            db, select(ScoringSchema).where(ScoringSchema.season_id == season_id)
        ),
        "scoring_formulas": await _rows(
            db, select(ScoringFormula).where(ScoringFormula.season_id == season_id)
        ),
        "bracket_weights": await _rows(
            db, select(ScoringBracketWeight).where(ScoringBracketWeight.season_id == season_id)
        ),
        # Metadata only: the stored file path is an implementation detail and
        # the PDFs themselves are not part of a JSON export.
        "papers": await _rows(
            db, select(Paper).where(Paper.season_id == season_id), exclude=("file_url",)
        ),
        "paper_status_history": await _rows(
            db, select(PaperStatusHistory).where(PaperStatusHistory.paper_id.in_(paper_ids))
        ),
        "print_jobs": await _rows(
            db, select(PrintJob).where(PrintJob.season_id == season_id), exclude=("file_url",)
        ),
    }
