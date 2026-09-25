"""Terminology tables (M24): generic ontology -> per-game vocabulary.

The chat system prompt injects a terminology block so the model speaks each
game's language; contract tests require every ontology key per adapter.
"""

from __future__ import annotations

import json
from importlib import resources
from typing import Any

REQUIRED_KEYS = (
    "character",
    "character_plural",
    "equipment",
    "equipment_plural",
    "gear",
    "gear_plural",
    "duplication",
    "special_progression",
    "team",
    "build",
    "role",
    "attribute",
    "pull_currency",
)


def load_terminology_table(game_package: str) -> list[dict[str, Any]]:
    """Load the adapter's terminology.json (empty list when not shipped yet)."""
    try:
        raw = (
            resources.files(f"game_companion.games.{game_package}")
            .joinpath("data", "terminology.json")
            .read_text(encoding="utf-8")
        )
    except (FileNotFoundError, ModuleNotFoundError):
        return []
    data = json.loads(raw)
    return [
        {"key": key, **(value or {})}
        for key, value in data.get("terms", {}).items()
    ]


def terminology_block(game_name: str, table: list[dict[str, Any]]) -> str:
    """Prompt text teaching the model the game's vocabulary."""
    if not table:
        return ""
    lines = [f"Terminology for {game_name} — use these names when speaking:"]
    for entry in table:
        gloss = entry.get("gloss") or ""
        line = f"- {entry['key']}: {entry.get('display', '')}"
        if gloss:
            line += f" ({gloss})"
        lines.append(line)
    return "\n".join(lines)
