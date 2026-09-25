"""Structured logging for the API, the Celery worker and beat.

structlog loggers and the standard library (uvicorn, SQLAlchemy, Celery, ...)
write through one handler whose formatter is structlog's ProcessorFormatter:
production output is one JSON object per line, development output the
console format. Entries written while a request is handled carry its
``request_id`` (bound by :class:`AccessLogMiddleware`).
"""

import logging
import sys
from time import perf_counter
from typing import Any

import structlog
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from core.config import get_settings

# Probes hit these every few seconds; their access-log lines are DEBUG only.
_QUIET_PATHS = frozenset({"/api/system/health", "/api/system/readiness", "/api/system/metrics"})


def _log_level() -> int:
    settings = get_settings()
    if settings.log_level:
        level = logging.getLevelName(settings.log_level.strip().upper())
        if isinstance(level, int):
            return level
    return logging.DEBUG if settings.is_dev else logging.INFO


def configure_logging() -> None:
    """Route structlog and stdlib logging through one structlog formatter."""
    settings = get_settings()
    level = _log_level()

    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
    ]
    renderer: list[Any] = (
        [structlog.dev.ConsoleRenderer()]
        if settings.is_dev
        else [structlog.processors.format_exc_info, structlog.processors.JSONRenderer()]
    )

    structlog.configure(
        processors=[*shared_processors, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=shared_processors,
            processors=[structlog.stdlib.ProcessorFormatter.remove_processors_meta, *renderer],
        )
    )
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)

    # uvicorn installs its own handlers before the app is imported; send its
    # records through the root handler instead. Its access log is replaced by
    # AccessLogMiddleware (which knows the request id).
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    # SQL statements (and the driver's chatter) only with DB_ECHO=true: logging
    # every statement with its rows slowed development instances down a lot.
    logging.getLogger("sqlalchemy.engine").setLevel(
        logging.INFO if settings.db_echo else logging.WARNING
    )
    logging.getLogger("aiosqlite").setLevel(logging.WARNING)


def get_logger(name: str = __name__) -> structlog.BoundLogger:
    return structlog.get_logger(name)


_access_logger = get_logger("access")


class AccessLogMiddleware:
    """Bind the request id to the log context and log one line per request.

    Runs inside the middleware that assigns ``request.state.request_id``, so
    every entry written while the request is handled carries the same id the
    client receives in ``X-Request-ID``.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = (scope.get("state") or {}).get("request_id")
        structlog.contextvars.clear_contextvars()
        if request_id:
            structlog.contextvars.bind_contextvars(request_id=request_id)

        status = 500
        started = perf_counter()

        async def send_with_status(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_with_status)
        finally:
            path = scope.get("path", "")
            log = _access_logger.debug if path in _QUIET_PATHS else _access_logger.info
            log(
                "request",
                method=scope.get("method"),
                path=path,
                status=status,
                duration_ms=round((perf_counter() - started) * 1000, 1),
            )
