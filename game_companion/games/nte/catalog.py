"""NTE catalog + codes sources (M25): Prydwen server-rendered pages.

Prydwen covers Neverness to Everness (agents + codes). Pages are static HTML
(no embedded JSON blob), so transforms parse the markup with tolerant regexes
against split card boundaries. Any layout change yields zero rows and an
honest error status — never garbage rows.

[verify] markers apply: NTE is unreleased/early-data; whatever Prydwen lists
is community-compiled and may shift.
"""

from __future__ import annotations

import re
from typing import Any

PRYDWEN_NTE = "https://www.prydwen.gg/neverness-to-everness"

CATALOG_SOURCES: dict[str, dict[str, Any]] = {
    "prydwen_characters": {
        "name": "Prydwen NTE character index",
        "url": f"{PRYDWEN_NTE}/characters",
        "kind": "html",
        "entity": "character",
        "notes": "community-compiled roster card: name/rarity/element/role",
    },
    "prydwen_banners": {
        "name": "Prydwen NTE banners",
        "url": f"{PRYDWEN_NTE}/banners",
        "kind": "html",
        "entity": "banner",
        "notes": "current/upcoming channels with NA-server date windows [verify: early data]",
    },
}

CODES_SOURCE: dict[str, Any] = {
    "key": "prydwen_codes",
    "name": "Prydwen NTE codes page",
    "url": f"{PRYDWEN_NTE}/codes",
    "kind": "html",
}

# Prydwen SSR emits each character as an anchor wrapping the avatar card:
# <a href=".../characters/SLUG"><div class="avatar pw-card nte rarity-X true">
# <img alt="Name" ...>...<span class="emp-name">Name</span>...element/role icons
_CARD_ANCHOR = re.compile(
    r'<a href="/neverness-to-everness/characters/([a-z0-9-]+)">'
    r'<div class="avatar pw-card nte rarity-(\w+)[^"]*">(.*?)</a>',
    re.S,
)
_ALTS = re.compile(r'alt="([^"]+)"')
_NTE_ROLES = ("Buff", "Damage", "Survival")


def catalog_transform(source_key: str, payload: Any) -> list[dict[str, Any]]:
    if source_key == "prydwen_banners":
        from game_companion.core.games.prydwen import parse_banners

        return parse_banners(payload) if isinstance(payload, str) else []
    if source_key != "prydwen_characters" or not isinstance(payload, str):
        return []
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for slug, rarity, body in _CARD_ANCHOR.findall(payload):
        name_match = re.search(r'<span class="emp-name">([^<]+)</span>', body)
        name = name_match.group(1).strip() if name_match else ""
        if not name or slug in seen:
            continue
        seen.add(slug)
        alts = _ALTS.findall(body)
        # alts[0] is the card image (= name); element and role follow as icons
        element = alts[1] if len(alts) > 1 else None
        role = next((a for a in alts[1:] if a in _NTE_ROLES), None)
        rows.append(
            {
                "key": slug,
                "name": name,
                "rarity": rarity,
                "meta": {"element": element, "role": role, "community_data": True},
                "source": "prydwen",
            }
        )
    return rows


def codes_transform(payload: Any) -> list[dict[str, Any]]:
    """Prydwen NTE codes page -> code rows (parser shared in core.games.prydwen)."""
    from game_companion.core.games.prydwen import parse_codes

    return parse_codes(payload) if isinstance(payload, str) else []
