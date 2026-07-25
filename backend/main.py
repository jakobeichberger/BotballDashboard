"""
BotballDashboard – FastAPI application entry point.

Start with:
    uvicorn main:app --host 0.0.0.0 --port 8000
Or via Docker (migrate-then-start.sh runs migrations first).
"""

import asyncio
import re
import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy.exc import IntegrityError

from core.config import get_settings
from core.logging import configure_logging
from core.metrics import observe_request, render_metrics
from core.modules import MODULES

settings = get_settings()
configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    from core.logging import get_logger

    get_logger("startup").info("BotballDashboard API starting", env=settings.app_env)
    yield
    get_logger("shutdown").info("BotballDashboard API stopped")


app = FastAPI(
    title="BotballDashboard API",
    version="1.0.0",
    docs_url="/api/docs" if settings.is_dev else None,
    redoc_url="/api/redoc" if settings.is_dev else None,
    openapi_url="/api/openapi.json" if settings.is_dev else None,
    lifespan=lifespan,
)


def _request_id(request: Request) -> str:
    candidate = request.headers.get("x-request-id", "")
    return candidate if re.fullmatch(r"[A-Za-z0-9._-]{1,64}", candidate) else str(uuid.uuid4())


@app.middleware("http")
async def request_context_and_security(request: Request, call_next):
    request.state.request_id = _request_id(request)
    try:
        content_length = int(request.headers.get("content-length", "0") or 0)
    except ValueError:
        content_length = 0
    if (
        request.method in {"POST", "PUT", "PATCH"}
        and content_length > (settings.max_upload_size_mb + 1) * 1024 * 1024
    ):
        return JSONResponse(
            status_code=413,
            content={
                "code": "request_too_large",
                "message": "Request exceeds the configured size limit.",
                "fieldErrors": {},
                "requestId": request.state.request_id,
            },
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
async def integrity_error_handler(request: Request, _exc: IntegrityError):
    """Convert constraint violations without leaking database internals."""
    request_id = (
        getattr(getattr(request, "state", None), "request_id", None)
        if request is not None
        else None
    ) or (str(uuid.uuid4()) if request is None else _request_id(request))
    return JSONResponse(
        status_code=409,
        content={
            "code": "data_conflict",
            "message": "Request violates a data constraint (missing reference or duplicate).",
            "fieldErrors": {},
            "requestId": request_id,
        },
    )


@app.middleware("http")
async def audit_successful_mutations(request: Request, call_next):
    """Record successful API mutations without making audit failures user-facing."""
    response = await call_next(request)
    if (
        not getattr(request.app.state, "testing", False)
        and request.method in {"POST", "PUT", "PATCH", "DELETE"}
        and request.url.path.startswith("/api/")
        and response.status_code < 400
    ):
        try:
            from core.audit import log_action
            from core.auth import decode_token
            from core.database import AsyncSessionLocal

            user_id = None
            authorization = request.headers.get("authorization", "")
            if authorization.lower().startswith("bearer "):
                try:
                    user_id = decode_token(authorization.split(" ", 1)[1]).get("sub")
                except Exception:
                    user_id = None
            async with AsyncSessionLocal() as session:
                await log_action(
                    session,
                    f"{request.method} {request.url.path}",
                    user_id=user_id,
                    resource_type="api",
                    resource_id=request.url.path,
                    ip_address=request.client.host if request.client else None,
                )
                await session.commit()
        except Exception:
            # User-facing mutations must not fail when audit storage is unavailable.
            pass
    return response


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
for module in MODULES:
    app.include_router(module.router, prefix="/api")


@app.get("/api/system/health", tags=["system"])
async def health():
    """Health check – no auth required."""
    return {"status": "ok", "version": app.version}


@app.get("/api/system/readiness", tags=["system"])
async def readiness():
    from redis.asyncio import Redis
    from sqlalchemy import text

    from core.celery_app import celery_app
    from core.database import engine

    checks: dict[str, bool] = {"postgresql": False, "redis": False, "worker": False}
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        checks["postgresql"] = True
    except Exception:
        pass
    redis = Redis.from_url(settings.redis_url)
    try:
        checks["redis"] = bool(await redis.ping())
    except Exception:
        pass
    finally:
        await redis.aclose()
    try:
        replies = await asyncio.wait_for(
            asyncio.to_thread(lambda: celery_app.control.inspect(timeout=1).ping()),
            timeout=2,
        )
        checks["worker"] = bool(replies)
    except Exception:
        pass
    ready = all(checks.values())
    return JSONResponse(
        status_code=200 if ready else 503,
        content={"status": "ready" if ready else "not_ready", "checks": checks},
    )


@app.get("/api/system/metrics", tags=["system"], response_class=PlainTextResponse)
async def metrics():
    return render_metrics()
