"""Static module registry for the BotballDashboard modular monolith."""

from dataclasses import dataclass

from fastapi import APIRouter

from modules.auth.routes import router as auth_router
from modules.dashboard.routes import router as dashboard_router
from modules.events.routes import public_router as public_events_router
from modules.events.routes import router as events_router
from modules.exports.routes import router as exports_router
from modules.paper_review.routes import router as paper_router
from modules.printing.routes import router as printing_router
from modules.scoring import router as scoring_router
from modules.scoring.score_sheets.scan_routes import router as score_scans_router
from modules.seasons.routes import router as seasons_router
from modules.teams.routes import router as teams_router


@dataclass(frozen=True)
class ModuleDefinition:
    key: str
    router: APIRouter
    permissions: tuple[str, ...] = ()


MODULES: tuple[ModuleDefinition, ...] = (
    ModuleDefinition("auth", auth_router),
    ModuleDefinition("seasons", seasons_router, ("seasons:read", "seasons:write")),
    ModuleDefinition("events", events_router, ("events:read", "events:write", "events:admin")),
    ModuleDefinition("public-events", public_events_router),
    ModuleDefinition("teams", teams_router, ("teams:read", "teams:write")),
    ModuleDefinition("scoring", scoring_router, ("scoring:read", "scoring:write", "scoring:admin")),
    ModuleDefinition("score-sheet-scans", score_scans_router, ("scoring:read", "scoring:write")),
    ModuleDefinition("papers", paper_router, ("papers:read", "papers:review", "papers:admin")),
    ModuleDefinition(
        "printing", printing_router, ("printing:read", "printing:write", "printing:admin")
    ),
    ModuleDefinition("dashboard", dashboard_router, ("dashboard:read",)),
    ModuleDefinition("exports", exports_router),
)
