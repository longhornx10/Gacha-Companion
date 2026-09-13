"""FastAPI application factory."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request

from game_companion.api.deps import domain_error_handler
from game_companion.api.routes import api_router
from game_companion.config import Settings, get_settings
from game_companion.core.llm.client import LLMClient
from game_companion.db.models import *  # noqa: F401,F403 - registers all tables
from game_companion.db.session import create_db_engine, create_session_factory
from game_companion.errors import DomainError
from game_companion.logging import setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: Settings = app.state.settings
    Path(settings.resolved_data_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.exports_dir).mkdir(parents=True, exist_ok=True)
    yield
    app.state.llm.close()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    setup_logging(settings)

    app = FastAPI(
        title="Gacha Companion",
        description=(
            "Local-first, game-agnostic gacha companion framework. "
            "Authoritative account state in SQLite; the LLM never owns your data."
        ),
        version="0.1.0",
        lifespan=lifespan,
    )

    engine = create_db_engine(settings.resolved_database_url)
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = create_session_factory(engine)
    app.state.llm = LLMClient(settings)

    app.include_router(api_router)
    app.add_exception_handler(DomainError, domain_error_handler)

    @app.get("/health")
    def root_health(request: Request):  # pragma: no cover - trivial
        return {"status": "ok", "service": "gacha-companion"}

    return app
