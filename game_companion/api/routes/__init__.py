"""Route registry."""

from fastapi import APIRouter

from game_companion.api.routes import (
    codes_history,
    exports,
    items,
    recommendations,
    research_vision,
    roster,
    system,
    teams_resources,
)

api_router = APIRouter(prefix="/api")
api_router.include_router(system.router)
api_router.include_router(roster.router)
api_router.include_router(items.router)
api_router.include_router(teams_resources.router)
api_router.include_router(codes_history.router)
api_router.include_router(research_vision.router)
api_router.include_router(recommendations.router)
api_router.include_router(exports.router)
