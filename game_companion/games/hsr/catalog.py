"""HSR catalog + codes sources (M25).

Catalog: StarRailRes (Mar-7th) index files — raw.githubusercontent.com JSON
per entity: characters, light cones, relic sets. Codes: Prydwen's Star Rail
hub page (no /codes subpage; the boxes live on the game home).

Shape-tolerant transforms — rows without a name are skipped, never guessed.
"""

from __future__ import annotations

from typing import Any


def codes_transform(payload: Any) -> list[dict[str, Any]]:
    """Prydwen hub HTML -> code rows (parser shared in core.games.prydwen)."""
    from game_companion.core.games.prydwen import parse_codes

    return parse_codes(payload) if isinstance(payload, str) else []

_STARRAILRES = "https://raw.githubusercontent.com/Mar-7th/StarRailRes/master/index_new/en"

CATALOG_SOURCES: dict[str, dict[str, Any]] = {
    "starrailres_characters": {
        "name": "StarRailRes character index",
        "url": f"{_STARRAILRES}/characters.json",
        "kind": "json",
        "entity": "character",
        "notes": "ids/names/rarities/paths/elements by character id",
    },
    "starrailres_light_cones": {
        "name": "StarRailRes light cone index",
        "url": f"{_STARRAILRES}/light_cones.json",
        "kind": "json",
        "entity": "equipment",
        "notes": "ids/names/rarities/paths by light cone id",
    },
    "starrailres_relic_sets": {
        "name": "StarRailRes relic set index",
        "url": f"{_STARRAILRES}/relic_sets.json",
        "kind": "json",
        "entity": "gear_set",
        "notes": "relic set ids/names/descriptions",
    },
    "prydwen_banners": {
        "name": "Prydwen Star Rail warp banners",
        "url": "https://www.prydwen.gg/star-rail/banners",
        "kind": "html",
        "entity": "banner",
        "notes": "current/upcoming character + light-cone warps with NA-server date windows",
    },
}

# Prydwen shows the current redeem codes on the game hub itself (there is no
# /codes subpage) — same box markup as the NTE codes page.
CODES_SOURCE: dict[str, Any] = {
    "key": "prydwen_codes",
    "name": "Prydwen Star Rail hub",
    "url": "https://www.prydwen.gg/star-rail",
    "kind": "html",
}


def catalog_transform(source_key: str, payload: Any) -> list[dict[str, Any]]:
    if source_key == "prydwen_banners":
        from game_companion.core.games.prydwen import parse_banners

        return parse_banners(payload) if isinstance(payload, str) else []
    if not isinstance(payload, dict):
        return []
    rows: list[dict[str, Any]] = []
    for key, item in payload.items():
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        if "{" in name:
            # StarRailRes ships ten trailblazer placeholders ({NICKNAME}); they
            # are the player, not a character — skip rather than display junk
            continue
        meta: dict[str, Any] = {}
        if source_key == "starrailres_characters":
            meta = {"path": item.get("path"), "element": item.get("element")}
        elif source_key == "starrailres_light_cones":
            meta = {"path": item.get("path"), "kind": "light_cone"}
        elif source_key == "starrailres_relic_sets":
            meta = {"descriptions": item.get("desc")}
        rows.append(
            {
                "key": str(item.get("id") or key),
                "name": name.strip(),
                "rarity": item.get("rarity") if isinstance(item.get("rarity"), int) else None,
                "meta": meta,
                "source": "starrailres",
            }
        )
    return rows
