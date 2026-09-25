"""Write responses leave only after the request's transaction is committed.

``get_db`` commits in the teardown of a ``yield`` dependency. Since FastAPI
0.12x such teardown runs *after* the response has been sent, so a client could
get its 201 and, with the very next request, still read the old state: create
a season and the season list does not show it yet, create a team and
registering it answers "Team not found". A commit that fails in the teardown
(a constraint only checked at COMMIT) would even leave the client with a
success status for a change that never happened.

CommitBeforeResponseMiddleware holds back the response of every write request
(POST, PUT, PATCH, DELETE) until the application – including the dependency
teardown, i.e. the commit – has finished, then sends it unchanged. If the
commit fails, the held response is dropped and the client gets the error
instead. Reads pass straight through; their responses, including the file
downloads, are never buffered.
"""

from sqlalchemy.exc import IntegrityError
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from core.logging import get_logger

logger = get_logger(__name__)

_WRITES = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def _integrity_error(exc: BaseException) -> IntegrityError | None:
    # Starlette re-raises a handled exception that arrives after the response
    # started as RuntimeError("… response already started") from the original.
    while exc is not None:
        if isinstance(exc, IntegrityError):
            return exc
        exc = exc.__cause__  # type: ignore[assignment]
    return None


class CommitBeforeResponseMiddleware:
    """Pure ASGI middleware: send a write response only once it is committed."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] not in _WRITES:
            await self.app(scope, receive, send)
            return

        held: list[Message] = []

        async def hold(message: Message) -> None:
            held.append(message)

        try:
            await self.app(scope, receive, hold)
        except Exception as exc:
            if not held:
                raise
            await self._commit_failed(scope, receive, send, exc)
            return
        for message in held:
            await send(message)

    @staticmethod
    async def _commit_failed(scope: Scope, receive: Receive, send: Send, exc: Exception) -> None:
        request_id = (scope.get("state") or {}).get("request_id")
        conflict = _integrity_error(exc)
        if conflict is not None:
            logger.warning(
                "integrity_error",
                path=scope.get("path"),
                request_id=request_id,
                error=str(conflict.orig)[:500],
            )
            status, code = 409, "data_conflict"
            message = "Request violates a data constraint (missing reference or duplicate)."
        else:
            logger.exception("commit_failed", path=scope.get("path"), request_id=request_id)
            status, code, message = 500, "internal_error", "Internal server error."
        response = JSONResponse(
            status_code=status,
            content={
                "code": code,
                "message": message,
                "fieldErrors": {},
                "requestId": request_id,
            },
        )
        await response(scope, receive, send)
