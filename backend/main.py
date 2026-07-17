"""
BotballDashboard – FastAPI application entry point.

Start with:
    uvicorn main:app --host 0.0.0.0 --port 8000
Or via Docker (migrate-then-start.sh runs migrations first).
"""

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from core.config import get_settings
from core.logging import configure_logging
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
# In dev: allow_origin_regex=".*" echoes back the actual Origin header so
# allow_credentials=True still works (allow_origins=["*"] would break cookies).
# In production: restrict to the explicit whitelist from ALLOWED_ORIGINS env var.
cors_options: dict[str, Any] = (
    {"allow_origin_regex": ".*"}
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
