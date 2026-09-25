"""Static module registry for the BotballDashboard modular monolith."""

from dataclasses import dataclass

from fastapi import APIRouter

from modules.auth.routes import router as auth_router
from modules.awards.routes import public_router as public_awards_router
from modules.awards.routes import router as awards_router
from modules.bots.routes import router as bots_router
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
    # Per-event module switch (modules.events.module_access) that gates every
    # route of this router; None for core modules that are always on.
    event_module: str | None = None


MODULES: tuple[ModuleDefinition, ...] = (
    ModuleDefinition("auth", auth_router),
    ModuleDefinition("seasons", seasons_router, ("seasons:read", "seasons:write")),
    ModuleDefinition("events", events_router, ("events:read", "events:write", "events:admin")),
    ModuleDefinition("public-events", public_events_router),
    ModuleDefinition("teams", teams_router, ("teams:read", "teams:write")),
    ModuleDefinition("scoring", scoring_router, ("scoring:read", "scoring:write", "scoring:admin")),
    ModuleDefinition("score-sheet-scans", score_scans_router, ("scoring:read", "scoring:write")),
    ModuleDefinition(
        "papers",
        paper_router,
        ("papers:read", "papers:write", "papers:review", "papers:admin"),
        event_module="paper",
    ),
    ModuleDefinition(
        "printing",
        printing_router,
        ("printing:read", "printing:write", "printing:admin"),
        event_module="printing",
    ),
    ModuleDefinition("dashboard", dashboard_router, ("dashboard:read", "dashboard:write")),
    ModuleDefinition("exports", exports_router),
    ModuleDefinition("awards", awards_router, ("awards:admin",)),
    ModuleDefinition("public-awards", public_awards_router),
    ModuleDefinition("bots", bots_router, ("teams:read", "teams:write"), event_module="bots"),
)
