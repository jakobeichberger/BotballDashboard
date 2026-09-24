"""Season/event lifecycle guards.

An archived season is read-only history: its events, registrations, matches,
results, papers and print jobs must not change any more. Every write service
that touches season- or event-scoped data calls ``ensure_writable`` first, so
the rule lives in one place instead of being re-implemented per module.

An event that is itself archived is read-only in the same way, except for the
event's own status (so it can be taken out of the archive again).
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.exceptions import ConflictError

ARCHIVED = "archived"
DRAFT = "draft"

ARCHIVED_SEASON_MESSAGE = "Season is archived and read-only"
ARCHIVED_EVENT_MESSAGE = "Event is archived and read-only"


async def ensure_writable(
    db: AsyncSession,
    *,
    season_id: str | None = None,
    event_id: str | None = None,
    allow_archived_event: bool = False,
) -> None:
    """Raise 409 when the season (or the event's season / the event) is archived.

    Unknown ids are ignored here – existence is the caller's concern and is
    reported with the caller's own 404.
    """
    from modules.events.models import Event
    from modules.seasons.models import Season

    # db.get consults the identity map first, so a status change made earlier
    # in the same unit of work (not yet flushed) is honoured.
    if event_id:
        event = await db.get(Event, event_id)
        if event is not None:
            if event.status == ARCHIVED and not allow_archived_event:
                raise ConflictError(ARCHIVED_EVENT_MESSAGE)
            if season_id is None:
                season_id = event.season_id
    if season_id:
        season = await db.get(Season, season_id)
        if season is not None and season.status == ARCHIVED:
            raise ConflictError(ARCHIVED_SEASON_MESSAGE)


async def season_has_data(db: AsyncSession, season_id: str) -> bool:
    """True when anything beyond configuration hangs off the season.

    Configuration (phases, deadlines, scoring schemas, formulas, empty events)
    may be deleted with the season; registrations, matches, results, papers,
    print jobs and schedules are tournament history and may not.
    """
    from modules.events.models import Event, EventRegistration, ScheduledMatch
    from modules.paper_review.models import Paper
    from modules.printing.models import PrintJob
    from modules.scoring.competition_models import AerialResult, DEResult, DocumentationScore
    from modules.scoring.models import Match, Ranking
    from modules.teams.models import TeamSeasonRegistration

    event_ids = select(Event.id).where(Event.season_id == season_id)
    probes = (
        select(Match.id).where(Match.season_id == season_id),
        select(Ranking.id).where(Ranking.season_id == season_id),
        select(DEResult.id).where(DEResult.season_id == season_id),
        select(AerialResult.id).where(AerialResult.season_id == season_id),
        select(DocumentationScore.id).where(DocumentationScore.season_id == season_id),
        select(Paper.id).where(Paper.season_id == season_id),
        select(PrintJob.id).where(PrintJob.season_id == season_id),
        select(TeamSeasonRegistration.id).where(TeamSeasonRegistration.season_id == season_id),
        select(EventRegistration.id).where(EventRegistration.event_id.in_(event_ids)),
        select(ScheduledMatch.id).where(ScheduledMatch.event_id.in_(event_ids)),
    )
    for probe in probes:
        if (await db.execute(probe.limit(1))).first() is not None:
            return True
    return False
