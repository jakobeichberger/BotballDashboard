"""Per-event module activation.

Which feature modules an event uses is decided by two switches:

* ``Event.active_modules`` — what the organizer enabled for this event
  (EventSetupPage), and
* the season's competition flags (``use_seeding``, ``use_double_elimination``,
  ``use_documentation_scoring``, ``use_aerial``) — a module the season does not
  run cannot be switched on for one of its events.

``paper`` (the paper-review workflow), ``printing`` and ``bots`` have no season
flag. ``use_paper_scoring`` only decides whether the paper score counts in the
overall formula; a season may review papers without scoring them.

Routes of a disabled module answer 404 for that event (see ``require_module``),
and the frontend hides their navigation entries and routes.
"""

from collections.abc import Awaitable, Callable

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import get_current_user
from core.database import get_db
from core.exceptions import ConflictError, NotFoundError
from modules.events.models import Event
from modules.seasons.models import Season

MODULE_KEYS: tuple[str, ...] = (
    "seeding",
    "double_elimination",
    "paper",
    "documentation",
    "aerial",
    "printing",
    "bots",
)

SEASON_FLAGS: dict[str, str] = {
    "seeding": "use_seeding",
    "double_elimination": "use_double_elimination",
    "documentation": "use_documentation_scoring",
    "aerial": "use_aerial",
}

# What a new event starts with: the core workflows. Competition extras (DE,
# documentation, aerial) are opted into per event.
DEFAULT_EVENT_MODULES: tuple[str, ...] = ("seeding", "paper", "printing", "bots")


def modules_for_season(season: Season | None) -> list[str]:
    """Default active modules of a new event in `season`: the core workflows
    plus every competition module the season has switched on."""
    modules = list(DEFAULT_EVENT_MODULES)
    if season is not None:
        for module, flag in SEASON_FLAGS.items():
            if getattr(season, flag) and module not in modules:
                modules.append(module)
        if not season.use_seeding:
            modules.remove("seeding")
    return [m for m in MODULE_KEYS if m in modules]


def effective_modules(event: Event, season: Season | None) -> list[str]:
    """Modules of `event` that are active *and* allowed by its season."""
    active = set(event.active_modules or [])
    result = []
    for module in MODULE_KEYS:
        if module not in active:
            continue
        flag = SEASON_FLAGS.get(module)
        if flag and season is not None and not getattr(season, flag):
            continue
        result.append(module)
    return result


async def event_modules(db: AsyncSession, event: Event) -> list[str]:
    season = await db.get(Season, event.season_id)
    return effective_modules(event, season)


def _disabled(module: str) -> NotFoundError:
    return NotFoundError(f"Module '{module}' is not active for this event")


async def assert_event_module(db: AsyncSession, event_id: str, module: str) -> None:
    """404 unless `module` is effective for the event. An unknown event is left
    to the route itself (it answers its own 404)."""
    event = await db.get(Event, event_id)
    if event is None:
        return
    if module not in await event_modules(db, event):
        raise _disabled(module)


PHASE_MODULES: dict[str, str] = {
    "seeding": "seeding",
    "double_seeding": "seeding",
    "double_elimination": "double_elimination",
}


async def assert_phase_allowed(db: AsyncSession, event: Event, phase_type: str) -> None:
    """409 when a phase of a disabled module is created or scheduled."""
    module = PHASE_MODULES.get(phase_type)
    if module and module not in await event_modules(db, event):
        raise ConflictError(f"Module '{module}' is not active for this event")


async def assert_season_module(db: AsyncSession, season_id: str, module: str) -> None:
    """For season-level requests that name no event: 404 when the season has
    events and none of them uses `module`."""
    season = await db.get(Season, season_id)
    if season is None:
        return
    events = list((await db.execute(select(Event).where(Event.season_id == season_id))).scalars())
    if events and not any(module in effective_modules(e, season) for e in events):
        raise _disabled(module)


async def default_event_id(db: AsyncSession, season_id: str) -> str | None:
    """The event season-scoped scoring routes write to (mirrors
    scoring.service.get_default_event, without creating one)."""
    result = await db.execute(
        select(Event.id)
        .where(Event.season_id == season_id)
        .order_by(Event.starts_at.asc().nullsfirst(), Event.created_at)
        .limit(1)
    )
    return result.scalar_one_or_none()


# ── Request guards ────────────────────────────────────────────────────────────

# Resolves (event_id, season_id) of the record a request addresses, from its
# path parameters (e.g. paper_id → Paper.event_id).
RecordResolver = Callable[[AsyncSession, dict], Awaitable[tuple[str | None, str | None]]]


async def _resolve_paper(db: AsyncSession, path: dict) -> tuple[str | None, str | None]:
    from modules.paper_review.models import Paper, PaperDeadline

    paper = await db.get(Paper, path["paper_id"]) if path.get("paper_id") else None
    if paper:
        return paper.event_id, paper.season_id
    deadline = await db.get(PaperDeadline, path["deadline_id"]) if path.get("deadline_id") else None
    return (None, deadline.season_id) if deadline else (None, None)


async def _resolve_print_job(db: AsyncSession, path: dict) -> tuple[str | None, str | None]:
    from modules.printing.models import PrintJob

    job = await db.get(PrintJob, path["job_id"]) if path.get("job_id") else None
    return (job.event_id, job.season_id) if job else (None, None)


async def _resolve_bot(db: AsyncSession, path: dict) -> tuple[str | None, str | None]:
    from modules.bots.models import Bot

    bot = await db.get(Bot, path["bot_id"]) if path.get("bot_id") else None
    return (None, bot.season_id) if bot else (None, None)


RECORD_RESOLVERS: dict[str, RecordResolver] = {
    "paper": _resolve_paper,
    "printing": _resolve_print_job,
    "bots": _resolve_bot,
}


async def _json_body(request: Request) -> dict:
    if request.method not in {"POST", "PUT", "PATCH"}:
        return {}
    if "application/json" not in request.headers.get("content-type", ""):
        return {}
    try:
        body = await request.json()  # cached by Starlette; the route reads it again
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}


async def gate_request(db: AsyncSession, request: Request, module: str) -> None:
    """Apply the module switch to whatever event (or season) `request` names.

    The event comes from the path, the query string, the JSON body or the
    addressed record, in that order. Requests that name no event fall back to
    the season rule; requests naming neither (printers, spools, the unfiltered
    list) are not event-scoped and pass.
    """
    path = dict(request.path_params)
    query = request.query_params
    body = await _json_body(request)
    event_id = path.get("event_id") or query.get("event_id") or body.get("event_id")
    season_id = path.get("season_id") or query.get("season_id") or body.get("season_id")
    resolver = RECORD_RESOLVERS.get(module)
    if not event_id and resolver:
        record_event, record_season = await resolver(db, path)
        event_id = record_event
        season_id = season_id or record_season
    if event_id:
        await assert_event_module(db, str(event_id), module)
    elif season_id:
        await assert_season_module(db, str(season_id), module)


def require_module(module: str) -> Callable[..., Awaitable[None]]:
    """Router-level guard for an authenticated feature module.

    Authentication runs first so anonymous callers get 401, not a hint about
    which modules an event uses.
    """

    async def _guard(
        request: Request,
        _user=Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> None:
        await gate_request(db, request, module)

    return _guard


def require_season_event_module(module: str) -> Callable[..., Awaitable[None]]:
    """Guard for the scoring result routes (DE, aerial, documentation).

    Event-scoped routes name their event in the path; season-scoped ones read
    and write the event named by ``?event_id=`` or else the season's default
    event, so that is the event whose switch applies.
    """

    async def _guard(request: Request, db: AsyncSession = Depends(get_db)) -> None:
        event_id = request.path_params.get("event_id") or request.query_params.get("event_id")
        season_id = request.path_params.get("season_id")
        if not event_id and season_id:
            event_id = await default_event_id(db, season_id)
        if event_id:
            await assert_event_module(db, event_id, module)

    return _guard
