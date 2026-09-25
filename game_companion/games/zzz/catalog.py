"""ZZZ catalog + codes sources (M25).

Catalog: Prydwen's Zenless pages (www.prydwen.gg/zenless/characters and
/zenless/w-engines) — server-rendered card markup, parsed with tolerant
regexes and fixture-tested. Chosen over hakush.in for the catalog because
hakush is unreachable on some networks (DNS); hakush stays wired into the
review-gated bootstrap flow separately. Codes: zenlesscodes.com's JSON API,
aggregated from multiple verified sources and auto-updated hourly via GitHub
Actions.

Transforms skip anything unparseable rather than guessing, so a layout
change yields zero rows and an honest error status — never garbage rows.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

PRYDWEN_ZENLESS = "https://www.prydwen.gg/zenless"

CATALOG_SOURCES: dict[str, dict[str, Any]] = {
    "prydwen_characters": {
        "name": "Prydwen Zenless agent index",
        "url": f"{PRYDWEN_ZENLESS}/characters",
        "kind": "html",
        "entity": "character",
        "notes": "agent cards: name/rank/element/specialty (community-compiled)",
    },
    "prydwen_wengines": {
        "name": "Prydwen Zenless W-Engine index",
        "url": f"{PRYDWEN_ZENLESS}/w-engines",
        "kind": "html",
        "entity": "equipment",
        "notes": "engine blocks: name/rank/specialty bonus type",
    },
    "prydwen_banners": {
        "name": "Prydwen Zenless warp banners",
        "url": f"{PRYDWEN_ZENLESS}/banners",
        "kind": "html",
        "entity": "banner",
        "notes": "current/upcoming channels with NA-server date windows (community-compiled)",
    },
}

CODES_SOURCE: dict[str, Any] = {
    "key": "zenlesscodes",
    "name": "zenlesscodes.com (hourly aggregated)",
    "url": "https://zenlesscodes.com/api/codes",
    "kind": "json",
}

# Prydwen rank letters -> the integer rarity scale used across the app.
_RANKS = {"S": 5, "A": 4, "B": 3}

_ZZZ_ELEMENTS = ("Physical", "Fire", "Ice", "Electric", "Ether")
_ZZZ_STYLES = ("Attack", "Stun", "Anomaly", "Support", "Defense", "Defence", "Rupture")

# <a href="/zenless/characters/SLUG"><div class="avatar pw-card zzz rarity-S true">
# <img alt="Name" ...>...<span class="emp-name">Name</span>...element/style icons
_CHAR_ANCHOR = re.compile(
    r'<a href="/zenless/characters/([a-z0-9-]+)">'
    r'<div class="avatar pw-card zzz rarity-(\w+)[^"]*">(.*?)</a>',
    re.S,
)
_ELEMENT_ALT = re.compile(r"(" + "|".join(_ZZZ_ELEMENTS) + r") element")
_STYLE_ALT = re.compile(r"(" + "|".join(_ZZZ_STYLES) + r") style", re.IGNORECASE)


def catalog_transform(source_key: str, payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, str):
        return []
    if source_key == "prydwen_characters":
        return _transform_characters(payload)
    if source_key == "prydwen_wengines":
        return _transform_wengines(payload)
    if source_key == "prydwen_banners":
        from game_companion.core.games.prydwen import parse_banners

        return parse_banners(payload)
    return []


def _transform_characters(payload: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for slug, rank, body in _CHAR_ANCHOR.findall(payload):
        name_match = re.search(r'<span class="emp-name">([^<]+)</span>', body)
        name = name_match.group(1).strip() if name_match else ""
        if not name or slug in seen:
            continue
        seen.add(slug)
        # starter-data key style: jane_doe, not jane-doe — keeps character_meta
        # resolution and scoring hooks working on catalog-created agents
        key = slug.replace("-", "_")
        element = _ELEMENT_ALT.search(body)
        style = _STYLE_ALT.search(body)
        specialty = style.group(1).lower() if style else None
        if specialty == "defence":
            specialty = "defense"  # Prydwen mixes British spelling
        rows.append(
            {
                "key": key,
                "name": name,
                "rarity": _RANKS.get(rank),
                "meta": {
                    "attribute": element.group(1).lower() if element else None,
                    "specialty": specialty,
                    "rank": rank,
                    "community_data": True,
                },
                "source": "prydwen",
            }
        )
    return rows


# <div class="zzz-engine"> ... <h5>Name</h5>
# Rarity: <strong class="rarity-S">S</strong> | Type: <strong class="type Attack">Attack</strong>
_ENGINE_SPLIT = re.compile(r'<div class="zzz-engine">')
_ENGINE_NAME = re.compile(r"<h5>([^<]+)")
_ENGINE_RANK = re.compile(r'zzz-icon rarity-(\w+)')
_ENGINE_TYPE = re.compile(r'class="type (\w+)"')
_ENGINE_SLUG = re.compile(r"w-engines(?:%2F|/)([a-z0-9-]+)_image\.webp")


def _transform_wengines(payload: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for block in _ENGINE_SPLIT.split(payload)[1:]:
        slug_match = _ENGINE_SLUG.search(block)
        name_match = _ENGINE_NAME.search(block)
        name = name_match.group(1).strip() if name_match else ""
        if not slug_match or not name or slug_match.group(1) in seen:
            continue
        slug = slug_match.group(1)
        seen.add(slug)
        rank_match = _ENGINE_RANK.search(block)
        type_match = _ENGINE_TYPE.search(block)
        rank = rank_match.group(1) if rank_match else None
        rows.append(
            {
                "key": slug.replace("-", "_"),
                "name": name,
                "rarity": _RANKS.get(rank) if rank else None,
                "meta": {
                    "kind": "wengine",
                    "bonus_type": type_match.group(1).lower() if type_match else None,
                    "rank": rank,
                    "community_data": True,
                },
                "source": "prydwen",
            }
        )
    return rows


def codes_transform(payload: Any) -> list[dict[str, Any]]:
    """zenlesscodes payload -> code rows (active + expired)."""
    if not isinstance(payload, dict):
        return []
    rows: list[dict[str, Any]] = []
    for section, status in (("codes", "active"), ("expired", "expired")):
        for item in payload.get(section) or []:
            if not isinstance(item, dict):
                continue
            code = str(item.get("code") or "").strip()
            if not code:
                continue
            discovered = None
            raw_date = str(item.get("discovered_date") or "").strip()
            if raw_date:
                try:
                    discovered = datetime.fromisoformat(raw_date)
                except ValueError:
                    discovered = None  # honest unknown beats a wrong guess
            rewards = item.get("rewards")
            rows.append(
                {
                    "code": code,
                    "rewards": rewards.strip() if isinstance(rewards, str) and rewards.strip() else None,
                    "status": status,
                    "discovered_at": discovered,
                    "source": "zenlesscodes",
                }
            )
    return rows
