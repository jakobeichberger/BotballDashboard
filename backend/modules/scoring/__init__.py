from fastapi import APIRouter

from modules.scoring.extras_routes import router as extras_router
from modules.scoring.formula_routes import router as formula_router
from modules.scoring.routes import router as scoring_router
from modules.scoring.score_sheets.routes import router as score_sheets_router

router = APIRouter()
router.include_router(scoring_router)
router.include_router(score_sheets_router)
router.include_router(formula_router)
router.include_router(extras_router)
