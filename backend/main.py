"""
BotballDashboard – FastAPI application entry point.

Start with:
    uvicorn main:app --host 0.0.0.0 --port 8000
Or via Docker (migrate-then-start.sh runs migrations first).
"""

import asyncio
import re
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from kombu.exceptions import KombuError
from redis.exceptions import RedisError
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from core.audit import AuditMiddleware
from core.config import get_settings
from core.exceptions import RequestTooLargeError
from core.logging import AccessLogMiddleware, configure_logging, get_logger
from core.metrics import observe_request, render_metrics
from core.modules import MODULES
from core.redis_client import REDIS_ERRORS
from core.request_limits import BodySizeLimitMiddleware, body_limit_bytes
from core.transactions import CommitBeforeResponseMiddleware
from modules.events.draft_access import hide_draft_events
from modules.events.module_access import require_module

settings = get_settings()
configure_logging()
logger = get_logger("api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    from core.live import drain_pending_publishes
    from core.task_queue import drain_pending_tasks

    get_logger("startup").info("BotballDashboard API starting", env=settings.app_env)
    yield
    # Live events and Celery tasks queued by the last commits are still being sent.
    await drain_pending_publishes()
    await drain_pending_tasks()
    get_logger("shutdown").info("BotballDashboard API stopped")


app = FastAPI(
    title="BotballDashboard API",
    version="1.0.0",
    docs_url="/api/docs" if settings.is_dev else None,
    redoc_url="/api/redoc" if settings.is_dev else None,
    openapi_url="/api/openapi.json" if settings.is_dev else None,
    lifespan=lifespan,
)

# Middleware, outermost first (Starlette runs the last one added outermost):
#   CORSMiddleware                 CORS headers, also on errors and 413s
#   AuditMiddleware                records successful mutations
#   request_context_and_security   request id, Content-Length limit, security headers
#   AccessLogMiddleware            binds the request id to every log line, logs the request
#   BodySizeLimitMiddleware        counts streamed body bytes, 413 past the limit
#   CommitBeforeResponseMiddleware holds write responses until get_db has committed


def _request_id(request: Request) -> str:
    candidate = request.headers.get("x-request-id", "")
    return candidate if re.fullmatch(r"[A-Za-z0-9._-]{1,64}", candidate) else str(uuid.uuid4())


# Innermost: a write response leaves only after the request's transaction is
# committed (core.transactions), so the next request already reads the change.
app.add_middleware(CommitBeforeResponseMiddleware)
# Counts the body bytes as they arrive (chunked requests carry no
# Content-Length). Inside everything but the commit guard: its 413 goes
# through the regular error handler with request id and CORS headers.
app.add_middleware(BodySizeLimitMiddleware)
# Inside request_context_and_security, so it sees the request id that
# middleware assigns; outside the body limit, so a 413 is logged as well.
app.add_middleware(AccessLogMiddleware)


@app.middleware("http")
async def request_context_and_security(request: Request, call_next):
    request.state.request_id = _request_id(request)
    try:
        content_length = int(request.headers.get("content-length", "0") or 0)
    except ValueError:
        content_length = 0
    # An honest Content-Length is refused up front, before anything is read.
    if content_length > body_limit_bytes(request.url.path):
        return JSONResponse(
            status_code=413, content=RequestTooLargeError.body(request.state.request_id)
        )
    response = await observe_request(request, call_next)
    response.headers["X-Request-ID"] = request.state.request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Permitted-Cross-Domain-Policies"] = "none"
    response.headers["Permissions-Policy"] = "camera=(self), microphone=(), geolocation=()"
    if not settings.is_dev:
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        )
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException):
    detail: dict[str, Any] = exc.detail if isinstance(exc.detail, dict) else {}
    message = detail.get("message") if detail else str(exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        headers=exc.headers,
        content={
            "code": detail.get("code", f"http_{exc.status_code}"),
            "message": message,
            "fieldErrors": detail.get("fieldErrors", {}),
            "requestId": getattr(request.state, "request_id", _request_id(request)),
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    fields: dict[str, list[str]] = {}
    for error in exc.errors():
        key = ".".join(str(item) for item in error["loc"] if item != "body")
        fields.setdefault(key or "request", []).append(error["msg"])
    return JSONResponse(
        status_code=422,
        content={
            "code": "validation_error",
            "message": "Request validation failed.",
            "fieldErrors": fields,
            "requestId": getattr(request.state, "request_id", _request_id(request)),
        },
    )


@app.exception_handler(IntegrityError)
async def integrity_error_handler(request: Request, exc: IntegrityError):
    """Convert constraint violations without leaking database internals."""
    request_id = (
        getattr(getattr(request, "state", None), "request_id", None)
        if request is not None
        else None
    ) or (str(uuid.uuid4()) if request is None else _request_id(request))
    # The client gets a generic message; the log keeps the constraint for debugging.
    logger.warning(
        "integrity_error",
        path=request.url.path if request is not None else None,
        request_id=request_id,
        error=str(exc.orig)[:500],
    )
    return JSONResponse(
        status_code=409,
        content={
            "code": "data_conflict",
            "message": "Request violates a data constraint (missing reference or duplicate).",
            "fieldErrors": {},
            "requestId": request_id,
        },
    )


# Record successful API mutations. The audit row is written in the request's
# own transaction (get_db) instead of a second session per write request; see
# core.audit.AuditMiddleware. Registered here to keep its place in the stack.
app.add_middleware(AuditMiddleware)


# CORS
# In dev: reflect only localhost origins (so credentials work) rather than any
# origin — prevents arbitrary sites from making credentialed requests to a
# developer's instance.
# In production: restrict to the explicit whitelist from ALLOWED_ORIGINS env var.
cors_options: dict[str, Any] = (
    {"allow_origin_regex": r"https?://(localhost|127\.0\.0\.1)(:\d+)?"}
    if settings.is_dev
    else {"allow_origins": settings.allowed_origins_list}
)
app.add_middleware(
    CORSMiddleware,
    **cors_options,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register all modules from one explicit, static registry.
# Feature modules carry a per-event switch; their guard answers 404 for events
# that have the module disabled.
# Every router also hides draft events from users without events:write
# (modules.events.draft_access).
for module in MODULES:
    guards = [Depends(hide_draft_events)]
    if module.event_module:
        guards.append(Depends(require_module(module.event_module)))
    app.include_router(module.router, prefix="/api", dependencies=guards)


@app.get("/api/system/health", tags=["system"])
async def health():
    """Health check – no auth required."""
    return {"status": "ok", "version": app.version}


# The worker check broadcasts over the broker; probes call readiness every few
# seconds, so its result is reused for a short while.
_WORKER_CHECK_TTL = 15.0
# How long the broadcast waits for replies. Running workers answer within
# milliseconds; waiting is the price of hearing from all of them (the first
# reply alone would hide a dead worker behind a live one).
_WORKER_REPLY_TIMEOUT = 1.0
_worker_check: tuple[float, dict[str, int]] | None = None


def _expected_queues() -> tuple[str, ...]:
    from core.celery_app import DEFAULT_QUEUE, OCR_QUEUE, PERIODIC_QUEUE

    return (DEFAULT_QUEUE, PERIODIC_QUEUE, OCR_QUEUE)


async def _queue_consumers() -> dict[str, int]:
    """Number of live workers consuming each Celery queue.

    Every worker is asked which queues it consumes, so a dead ``worker``
    (default, periodic) is noticed while ``worker-ocr`` still answers, and
    the other way round.
    """
    global _worker_check
    now = time.monotonic()
    if _worker_check and now - _worker_check[0] < _WORKER_CHECK_TTL:
        return _worker_check[1]

    from core.celery_app import celery_app

    counts = dict.fromkeys(_expected_queues(), 0)
    try:
        replies = await asyncio.wait_for(
            asyncio.to_thread(
                lambda: celery_app.control.inspect(timeout=_WORKER_REPLY_TIMEOUT).active_queues()
            ),
            timeout=_WORKER_REPLY_TIMEOUT + 2,
        )
        for queues in (replies or {}).values():
            for name in {queue.get("name") for queue in queues or []}:
                if name in counts:
                    counts[name] += 1
    except (KombuError, RedisError, OSError, TimeoutError) as exc:  # broker unreachable
        logger.warning("readiness_worker_check_failed", error=str(exc))
    missing = sorted(name for name, count in counts.items() if count == 0)
    if missing:
        logger.warning("readiness_queue_without_worker", queues=missing)
    _worker_check = (time.monotonic(), counts)
    return counts


async def _beat_heartbeat() -> float | None:
    """Unix time beat last handed a task to the broker; None when unknown."""
    from redis.asyncio import Redis

    from core.celery_app import BEAT_HEARTBEAT_KEY

    redis = Redis.from_url(settings.redis_url)
    try:
        value = await redis.get(BEAT_HEARTBEAT_KEY)
    except REDIS_ERRORS as exc:
        logger.warning("beat_heartbeat_read_failed", error=str(exc))
        return None
    finally:
        await redis.aclose()
    try:
        return float(value) if value is not None else None
    except ValueError:
        return None


def _operational_metrics(consumers: dict[str, int], beat: float | None) -> str:
    lines = [
        "# HELP botball_celery_queue_consumers Live Celery workers consuming each queue.",
        "# TYPE botball_celery_queue_consumers gauge",
        *(
            f'botball_celery_queue_consumers{{queue="{name}"}} {count}'
            for name, count in sorted(consumers.items())
        ),
        "# HELP botball_beat_heartbeat_known 1 when Celery beat has left a heartbeat in Redis.",
        "# TYPE botball_beat_heartbeat_known gauge",
        f"botball_beat_heartbeat_known {0 if beat is None else 1}",
        "# HELP botball_beat_last_heartbeat_timestamp_seconds Last time beat handed a task"
        " to the broker.",
        "# TYPE botball_beat_last_heartbeat_timestamp_seconds gauge",
    ]
    if beat is not None:
        lines.append(f"botball_beat_last_heartbeat_timestamp_seconds {beat}")
    return "\n".join(lines) + "\n"


@app.get("/api/system/readiness", tags=["system"])
async def readiness() -> JSONResponse:
    from redis.asyncio import Redis
    from sqlalchemy import text

    from core.database import engine

    checks: dict[str, bool] = {"postgresql": False, "redis": False, "worker": False}
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        checks["postgresql"] = True
    except (SQLAlchemyError, OSError, TimeoutError) as exc:
        logger.warning("readiness_postgresql_failed", error=str(exc))
    redis = Redis.from_url(settings.redis_url)
    try:
        checks["redis"] = bool(await redis.ping())
    except REDIS_ERRORS as exc:
        logger.warning("readiness_redis_failed", error=str(exc))
    finally:
        await redis.aclose()
    queues = {name: count > 0 for name, count in (await _queue_consumers()).items()}
    # "worker" summarises the queues: each one has at least one live consumer.
    checks["worker"] = all(queues.values())
    ready = all(checks.values())
    return JSONResponse(
        status_code=200 if ready else 503,
        content={"status": "ready" if ready else "not_ready", "checks": checks, "queues": queues},
    )


@app.get("/api/system/metrics", tags=["system"], response_class=PlainTextResponse)
async def metrics(request: Request):
    # Prometheus scrapes backend:8000 on the internal network. Traefik excludes
    # this path from the public router; as a second line, refuse anything that
    # arrived through a proxy (which always sets X-Forwarded-For).
    if "x-forwarded-for" in request.headers:
        from core.exceptions import NotFoundError

        raise NotFoundError("Not found")
    # Queue consumers and the beat heartbeat drive the per-queue and beat
    # alerts (monitoring/alerts.yml); the queue check shares readiness' cache.
    return render_metrics() + _operational_metrics(
        await _queue_consumers(), await _beat_heartbeat()
    )
