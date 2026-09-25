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
from sqlalchemy.exc import IntegrityError

from core.audit import AuditMiddleware
from core.config import get_settings
from core.exceptions import RequestTooLargeError
from core.logging import AccessLogMiddleware, configure_logging, get_logger
from core.metrics import observe_request, render_metrics
from core.modules import MODULES
from core.request_limits import BodySizeLimitMiddleware, body_limit_bytes
from modules.events.draft_access import hide_draft_events
from modules.events.module_access import require_module

settings = get_settings()
configure_logging()
logger = get_logger("api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    from core.live import drain_pending_publishes

    get_logger("startup").info("BotballDashboard API starting", env=settings.app_env)
    yield
    # Live events queued by the last commits are still being published.
    await drain_pending_publishes()
    get_logger("shutdown").info("BotballDashboard API stopped")


app = FastAPI(
    title="BotballDashboard API",
    version="1.0.0",
    docs_url="/api/docs" if settings.is_dev else None,
    redoc_url="/api/redoc" if settings.is_dev else None,
    openapi_url="/api/openapi.json" if settings.is_dev else None,
    lifespan=lifespan,
)
# Registered first, so it runs inside request_context_and_security and sees the
# request id that middleware assigns.
app.add_middleware(AccessLogMiddleware)


def _request_id(request: Request) -> str:
    candidate = request.headers.get("x-request-id", "")
    return candidate if re.fullmatch(r"[A-Za-z0-9._-]{1,64}", candidate) else str(uuid.uuid4())


# Counts the body bytes as they arrive (chunked requests carry no
# Content-Length). Added first, so it is the innermost middleware: its 413 goes
# through the regular error handler with request id and CORS headers.
app.add_middleware(BodySizeLimitMiddleware)


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
_worker_check: tuple[float, bool] | None = None


async def _worker_alive() -> bool:
    global _worker_check
    now = time.monotonic()
    if _worker_check and now - _worker_check[0] < _WORKER_CHECK_TTL:
        return _worker_check[1]

    from core.celery_app import celery_app

    try:
        # limit=1: return as soon as one worker answers instead of waiting out
        # the timeout for replies from every worker.
        replies = await asyncio.wait_for(
            asyncio.to_thread(lambda: celery_app.control.ping(timeout=1.0, limit=1)),
            timeout=2,
        )
        alive = bool(replies)
    except Exception as exc:  # noqa: BLE001 - any broker error means "not ready"
        logger.warning("readiness_worker_check_failed", error=str(exc))
        alive = False
    _worker_check = (time.monotonic(), alive)
    return alive


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
    except Exception as exc:  # noqa: BLE001 - reported as a failed check
        logger.warning("readiness_postgresql_failed", error=str(exc))
    redis = Redis.from_url(settings.redis_url)
    try:
        checks["redis"] = bool(await redis.ping())
    except Exception as exc:  # noqa: BLE001 - reported as a failed check
        logger.warning("readiness_redis_failed", error=str(exc))
    finally:
        await redis.aclose()
    checks["worker"] = await _worker_alive()
    ready = all(checks.values())
    return JSONResponse(
        status_code=200 if ready else 503,
        content={"status": "ready" if ready else "not_ready", "checks": checks},
    )


@app.get("/api/system/metrics", tags=["system"], response_class=PlainTextResponse)
async def metrics(request: Request):
    # Prometheus scrapes backend:8000 on the internal network. Traefik excludes
    # this path from the public router; as a second line, refuse anything that
    # arrived through a proxy (which always sets X-Forwarded-For).
    if "x-forwarded-for" in request.headers:
        from core.exceptions import NotFoundError

        raise NotFoundError("Not found")
    return render_metrics()
