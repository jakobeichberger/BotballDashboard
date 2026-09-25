"""Draft events stay invisible to users without events:write.

``GET /v1/events`` and ``GET /v1/events/{id}`` already hid draft events (and
every event of a draft season) from guests and mentors, but the event's
sub-routes (registrations, schedule, rankings, scoring, …) served them to
anyone who knew or guessed the id — for instance from ``/scoring/schemas``.

``hide_draft_events`` is attached to every API router (see main.py). For a
read (GET/HEAD) that names an event in its path or as ``?event_id=``, it
answers 404 when the event is a draft and the caller lacks events:write.
Writes keep their own permission checks; anonymous requests are left to the
route, which answers 401 (or serves a public scoreboard, never a draft one).
"""

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import HTTPConnection

from core.auth import get_current_user, has_elevated_access
from core.database import get_db
from core.exceptions import NotFoundError
from modules.events.models import Event
from modules.seasons.lifecycle import DRAFT
from modules.seasons.models import Season

#: Who works on events before they are published (organizers, jurors).
DRAFT_READERS = "events:write"

_READ_METHODS = frozenset({"GET", "HEAD"})


async def is_draft_event(db: AsyncSession, event_id: str) -> bool:
    """True for a draft event and for any event of a draft season."""
    row = (
        await db.execute(
            select(Event.status, Season.status)
            .join(Season, Season.id == Event.season_id)
            .where(Event.id == event_id)
        )
    ).first()
    return row is not None and DRAFT in (row[0], row[1])


def _bearer_token(connection: HTTPConnection) -> str | None:
    scheme, _, token = connection.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer":
        return None
    return token.strip() or None


async def hide_draft_events(connection: HTTPConnection, db: AsyncSession = Depends(get_db)) -> None:
    # HTTPConnection (not Request) so the guard also fits WebSocket routes.
    if connection.scope["type"] != "http" or connection.scope["method"] not in _READ_METHODS:
        return
    event_id = connection.path_params.get("event_id") or connection.query_params.get("event_id")
    token = _bearer_token(connection)
    if not event_id or token is None or not await is_draft_event(db, str(event_id)):
        return
    user = await get_current_user(
        HTTPAuthorizationCredentials(scheme="Bearer", credentials=token), db
    )
    if not await has_elevated_access(db, user, DRAFT_READERS):
        raise NotFoundError("Event not found")
