"""Request body size limits, enforced while the body streams in.

A Content-Length check alone is not enough: a chunked request has no
Content-Length, and Starlette would buffer the whole body (JSON, form or
multipart) before the route — and before authentication — ever runs.
BodySizeLimitMiddleware counts the bytes the application actually receives and
aborts with 413 as soon as the limit is passed, whatever the headers claim.
"""

import re

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from core.config import get_settings
from core.exceptions import RequestTooLargeError

# Print job files (STL/3MF/G-code) have their own, larger limit
# (PRINT_UPLOAD_MAX_MB); the upload route enforces it exactly while streaming.
_PRINT_UPLOAD_PATH = re.compile(r"/api/printing/jobs/[^/]+/file")

# Multipart framing and form fields around an upload of exactly the limit.
_OVERHEAD_BYTES = 1024 * 1024


def body_limit_bytes(path: str) -> int:
    """Largest request body accepted for `path` (upload limit + framing)."""
    settings = get_settings()
    limit_mb = (
        settings.print_upload_max_mb
        if _PRINT_UPLOAD_PATH.fullmatch(path)
        else settings.max_upload_size_mb
    )
    return limit_mb * 1024 * 1024 + _OVERHEAD_BYTES


class BodySizeLimitMiddleware:
    """Pure ASGI middleware: count received body bytes, 413 past the limit.

    The overflow is raised from ``receive`` as an HTTPException (413), so it
    reaches the regular error handler wherever the body is read — FastAPI's
    body parsing re-raises HTTPExceptions unchanged. Should it escape anyway
    (e.g. from a streaming route), the middleware answers 413 itself as long as
    no response has started yet.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        limit = body_limit_bytes(scope["path"])
        received = 0
        response_started = False

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise RequestTooLargeError()
            return message

        async def tracking_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracking_send)
        except RequestTooLargeError:
            if response_started:
                return
            from starlette.responses import JSONResponse

            request_id = (scope.get("state") or {}).get("request_id")
            response = JSONResponse(status_code=413, content=RequestTooLargeError.body(request_id))
            await response(scope, receive, send)
