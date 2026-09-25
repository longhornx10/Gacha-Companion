"""Bootstrap sources + transforms for HSR (M24).

`game-companion bootstrap-game hsr` fetches structured JSON (StarRailRes by
default), transforms it into per-entity rows, and stages every difference as a
reviewable change record — never a silent overwrite. All fetches go through an
httpx client (transport injectable for offline tests).
"""

from __future__ import annotations

from typing import Any

BOOTSTRAP_SOURCES: dict[str, dict[str, Any]] = {
    "starrailres": {
        "name": "StarRailRes (Mar-7th) character index",
        "url": "https://raw.githubusercontent.com/Mar-7th/StarRailRes/master/index_new/en/characters.json",
        "kind": "json",
        "entity": "character_meta",
        "notes": "multilang character index; names/paths/elements by id",
    },
}


def transform(source_key: str, payload: Any) -> list[dict[str, Any]]:
    """Source payload -> normalized rows: {key, name, path, combat_type, rarity}."""
    if source_key != "starrailres":
        return []
    rows: list[dict[str, Any]] = []
    if isinstance(payload, dict):
        items = payload.items()
    elif isinstance(payload, list):
        items = [(str(i), item) for i, item in enumerate(payload)]
    else:
        return []
    for key, item in items:
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "key": str(item.get("id") or key),
                "name": item.get("name"),
                "path": item.get("path"),
                "combat_type": item.get("element"),
                "rarity": item.get("rarity"),
                "source": "starrailres",
            }
        )
    return rows
