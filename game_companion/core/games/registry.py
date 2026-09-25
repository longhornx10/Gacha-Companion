"""Game adapter registry.

The registry maps game ids to adapter classes *by import path string* and
instantiates them lazily — importing ``game_companion.core.games.registry``
must not import any game package. Plugins/tests can :func:`register` extra
adapters at runtime.
"""

from __future__ import annotations

import importlib
import json
import logging
import threading
from pathlib import Path

from game_companion.core.games.base import GameAdapter
from game_companion.errors import DomainError, NotFoundError

logger = logging.getLogger(__name__)

#: game_id -> "module:ClassName"
ADAPTER_ENTRYPOINTS: dict[str, str] = {
    "zzz": "game_companion.games.zzz.adapter:ZZZAdapter",
    "example": "game_companion.games.example_game.adapter:ExampleGameAdapter",
}

# Adapters installed by `game-companion new-game` register here (file-based,
# so scaffolding doesn't need to edit Python source).
INSTALLED_FILE = Path(__file__).resolve().parent.parent.parent / "games" / "installed.json"


def _installed_entrypoints() -> dict[str, str]:
    if not INSTALLED_FILE.exists():
        return {}
    try:
        data = json.loads(INSTALLED_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    adapters = data.get("adapters", {})
    return {str(k): str(v) for k, v in adapters.items() if isinstance(v, str)}

_lock = threading.Lock()
_extra: dict[str, str] = {}
_instances: dict[str, GameAdapter] = {}
_broken: dict[str, str] = {}


def register(game_id: str, import_path: str) -> None:
    """Register (or override) an adapter import path for ``game_id``."""
    with _lock:
        _extra[game_id] = import_path
        _instances.pop(game_id, None)
        _broken.pop(game_id, None)


def _entrypoints() -> dict[str, str]:
    return {**ADAPTER_ENTRYPOINTS, **_installed_entrypoints(), **_extra}


def get_adapter(game_id: str) -> GameAdapter:
    game_id = game_id.strip().lower()
    with _lock:
        cached = _instances.get(game_id)
        broken = _broken.get(game_id)
    if cached is not None:
        return cached
    if broken is not None:
        raise DomainError(
            f"game '{game_id}' is installed but broken: {broken}. "
            "Fix or remove its entry in games/installed.json."
        )
    entrypoints = _entrypoints()
    if game_id not in entrypoints:
        raise NotFoundError(f"unknown game '{game_id}' (available: {', '.join(sorted(entrypoints))})")
    module_name, _, class_name = entrypoints[game_id].partition(":")
    try:
        module = importlib.import_module(module_name)
        adapter_cls = getattr(module, class_name)
        adapter = adapter_cls()
    except Exception as exc:  # noqa: BLE001 — one bad adapter must not take down
        # health/games/the whole UI; remember it, skip it everywhere else
        with _lock:
            _broken[game_id] = f"{type(exc).__name__}: {exc}"
        logger.warning("adapter '%s' failed to load (%s: %s) — skipping",
                       game_id, type(exc).__name__, exc)
        raise DomainError(
            f"game '{game_id}' is installed but broken: {type(exc).__name__}: {exc}. "
            "Fix or remove its entry in games/installed.json."
        ) from exc
    with _lock:
        _instances[game_id] = adapter
    return adapter


def adapter_ids(include_hidden: bool = False) -> list[str]:
    """Registered game ids that actually load; broken ones are skipped (logged).

    Internal adapters are hidden unless asked for. A broken installed adapter
    is isolated here instead of failing /api/health, /api/games, every page
    and the refresh scheduler for all games.
    """
    ids = []
    for gid in sorted(_entrypoints()):
        try:
            adapter = get_adapter(gid)
        except Exception:  # noqa: BLE001 — broken adapters are logged in get_adapter
            continue
        if include_hidden or not adapter.hidden:
            ids.append(gid)
    return ids


def list_adapters(include_hidden: bool = False) -> list[GameAdapter]:
    return [get_adapter(gid) for gid in adapter_ids(include_hidden)]
