"""FastAPI dependencies."""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from starlette.responses import JSONResponse

from game_companion.config import Settings, get_settings
from game_companion.core.games.base import GameAdapter
from game_companion.core.games.registry import get_adapter
from game_companion.db.models import PlayerProfile
from game_companion.db.repositories import PlayerRepository
from game_companion.errors import DomainError


def settings_dep() -> Settings:
    return get_settings()


def get_db(request: Request) -> Iterator[Session]:
    """One session per request; commit on success, roll back on error."""
    factory = request.app.state.session_factory
    session = factory()
    try:
        yield session
        session.commit()
    except DomainError:
        session.rollback()
        raise
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def adapter_for(game_id: str) -> GameAdapter:
    return get_adapter(game_id)


def resolve_player(
    request: Request,
    session: Session = Depends(get_db),
    query_player: str | None = Query(default=None, alias="player_id"),
) -> PlayerProfile:
    """Player scoping: ``player_id`` path/query param, else the sole profile."""
    repo = PlayerRepository(session)
    player_id = request.path_params.get("player_id") or query_player
    if player_id:
        profile = repo.get(player_id)
        if profile is None:
            raise HTTPException(status_code=404, detail=f"player '{player_id}' not found")
        return profile
    return repo.require_sole()


def domain_error_handler(request: Request, exc: DomainError):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": {"error": type(exc).__name__, "message": exc.detail}},
    )
