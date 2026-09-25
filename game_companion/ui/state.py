"""UI session state: active player + active game for the local web UI.

Selections live in ``<data_dir>/ui-state.json`` (not per-player preferences —
the "which player is active" choice can't itself live on a player). Missing or
stale state falls back to the sole/first profile; no state is invented when no
profiles exist (the UI shows first-run setup instead).
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field

from game_companion.config import Settings
from game_companion.core.games.registry import adapter_ids
from game_companion.db.models import PlayerProfile
from game_companion.db.repositories import PlayerRepository
from game_companion.errors import ValidationError

STATE_FILENAME = "ui-state.json"
_lock = threading.Lock()


@dataclass
class UiState:
    player_id: str | None = None
    active_game: str | None = None

    def to_json(self) -> str:
        return json.dumps({"player_id": self.player_id, "active_game": self.active_game})


@dataclass
class UiContext:
    player: PlayerProfile | None
    active_game: str
    players: list[PlayerProfile] = field(default_factory=list)

    @property
    def needs_setup(self) -> bool:
        return self.player is None


def _state_path(settings: Settings):
    return settings.resolved_data_dir / STATE_FILENAME


def read_state(settings: Settings) -> UiState:
    path = _state_path(settings)
    if not path.exists():
        return UiState()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return UiState()
    return UiState(
        player_id=raw.get("player_id") or None,
        active_game=raw.get("active_game") or None,
    )


def write_state(settings: Settings, state: UiState) -> None:
    path = _state_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        path.write_text(state.to_json(), encoding="utf-8")


def resolve_context(settings: Settings, session) -> UiContext:
    players = list(PlayerRepository(session).list_all())
    state = read_state(settings)

    player = None
    if players:
        player = next((p for p in players if p.id == state.player_id), None)
        if player is None:
            # sole profile wins; otherwise the earliest created becomes active
            player = players[0]
            write_state(settings, UiState(player_id=player.id, active_game=state.active_game))

    game = state.active_game
    known = adapter_ids(include_hidden=True)
    if game not in known:
        game = "zzz" if "zzz" in known else sorted(known)[0]
    return UiContext(player=player, active_game=game, players=players)


def select_game(settings: Settings, session, game_id: str) -> UiContext:
    if game_id not in adapter_ids(include_hidden=True):
        raise ValidationError(f"unknown game '{game_id}'")
    state = read_state(settings)
    state.active_game = game_id
    write_state(settings, state)
    return resolve_context(settings, session)


def select_player(settings: Settings, session, player_id: str) -> UiContext:
    player = PlayerRepository(session).get(player_id)
    if player is None:
        raise ValidationError(f"player '{player_id}' not found")
    state = read_state(settings)
    state.player_id = player_id
    write_state(settings, state)
    return resolve_context(settings, session)
