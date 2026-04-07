"""
BotballDashboard – FastAPI application entry point.

Start with:
    uvicorn main:app --host 0.0.0.0 --port 8000
Or via Docker (migrate-then-start.sh runs migrations first).
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.config import get_settings
from core.logging import configure_logging

# Module routers
from modules.auth.routes import router as auth_router
from modules.seasons.routes import router as seasons_router
from modules.teams.routes import router as teams_router
from modules.scoring import router as scoring_router
from modules.paper_review.routes import router as paper_router
from modules.printing.routes import router as printing_router
from modules.dashboard.routes import router as dashboard_router
from modules.exports.routes import router as exports_router

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

# CORS
# In dev: allow_origin_regex=".*" echoes back the actual Origin header so
# allow_credentials=True still works (allow_origins=["*"] would break cookies).
# In production: restrict to the explicit whitelist from ALLOWED_ORIGINS env var.
app.add_middleware(
    CORSMiddleware,
    **({"allow_origin_regex": ".*"} if settings.is_dev else {"allow_origins": settings.allowed_origins_list}),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register all module routers under /api
app.include_router(auth_router, prefix="/api")
app.include_router(seasons_router, prefix="/api")
app.include_router(teams_router, prefix="/api")
app.include_router(scoring_router, prefix="/api")
app.include_router(paper_router, prefix="/api")
app.include_router(printing_router, prefix="/api")
app.include_router(dashboard_router, prefix="/api")
app.include_router(exports_router, prefix="/api")


@app.get("/api/system/health", tags=["system"])
async def health():
    """Health check – no auth required."""
    return {"status": "ok", "version": app.version}
