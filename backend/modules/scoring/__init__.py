"""
Scoring Module – aggregates all sub-routers.

Import this router in the main FastAPI application:

    from modules.scoring import router as scoring_router
    app.include_router(scoring_router, prefix="/api")
"""

from fastapi import APIRouter

from .score_sheets.routes import router as score_sheets_router

# Main scoring router – further sub-routers (matches, ranking, …) added here
router = APIRouter()
router.include_router(score_sheets_router)
