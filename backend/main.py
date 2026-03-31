"""
BotballDashboard – FastAPI application entry point.

Start with:
    uvicorn main:app --host 0.0.0.0 --port 8000
Or via Docker (migrate-then-start.sh runs migrations first).
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os

# Module routers
from modules.scoring import router as scoring_router
# from modules.paper_review import router as paper_review_router  # add when implemented
# from modules.print import router as print_router                # add when implemented

app = FastAPI(
    title="BotballDashboard API",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

# CORS – allow the configured frontend origin(s)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:5173").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register all module routers under /api
app.include_router(scoring_router, prefix="/api")
# app.include_router(paper_review_router, prefix="/api")
# app.include_router(print_router, prefix="/api")


@app.get("/api/system/health", tags=["system"])
async def health():
    """Health check – no auth required. Used by Traefik / Uptime Kuma."""
    return {"status": "ok", "version": app.version}
