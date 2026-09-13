"""Game manifest loading (TOML metadata shipped inside each adapter package)."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from importlib import resources
from typing import Any


@dataclass(frozen=True)
class GameManifest:
    game_id: str
    display_name: str
    version: str
    summary: str
    extra: dict[str, Any]


def load_manifest(package: str, filename: str = "manifest.toml") -> GameManifest:
    text = resources.files(package).joinpath(filename).read_text(encoding="utf-8")
    raw = tomllib.loads(text)
    game = raw.get("game", {})
    return GameManifest(
        game_id=str(game["game_id"]),
        display_name=str(game.get("display_name", game["game_id"])),
        version=str(game.get("version", "0")),
        summary=str(game.get("summary", "")),
        extra={k: v for k, v in raw.items() if k != "game"},
    )
