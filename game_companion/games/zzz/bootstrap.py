"""ZZZ bootstrap sources (M24 follow-up): new-character detection.

hakush.in's ZZZ dataset is the documented machine-readable source (see
seriaati/hakushin-py). The transformer is deliberately shape-tolerant: hakush
has changed field shapes before, and anything unparseable is skipped rather
than guessed. New agent ids arrive as pending change records for review.
"""

from __future__ import annotations

from typing import Any

BOOTSTRAP_SOURCES: dict[str, dict[str, Any]] = {
    "hakush": {
        "name": "hakush.in ZZZ character index",
        "url": "https://api.hakush.in/zzz/data/character.json",
        "kind": "json",
        "entity": "character_meta",
        "notes": "new-character detection; ids/names/ranks/elements by agent id",
    },
}

_ELEMENT_NAMES = {
    "physical": "Physical", "fire": "Fire", "ice": "Ice",
    "electric": "Electric", "ether": "Ether",
    200: "Physical", 201: "Fire", 202: "Ice", 203: "Electric", 205: "Ether",
}


def transform(source_key: str, payload: Any) -> list[dict[str, Any]]:
    if source_key != "hakush" or not isinstance(payload, dict):
        return []
    rows: list[dict[str, Any]] = []
    for key, item in payload.items():
        if not isinstance(item, dict):
            continue
        name = item.get("name") or item.get("full_name")
        if not name:
            continue  # cannot review a row without a name — skip, never guess
        rank = item.get("rank") or item.get("rarity")
        element = item.get("element") or item.get("attribute")
        if isinstance(element, dict):  # some shapes nest {name: ...} or {id: ...}
            element = element.get("name") or element.get("id")
        if isinstance(element, int):
            element = _ELEMENT_NAMES.get(element, str(element))
        if isinstance(element, str):
            element = element.lower()
        specialty = item.get("type") or item.get("specialty")
        if isinstance(specialty, dict):
            specialty = specialty.get("name")
        if isinstance(specialty, str):
            specialty = specialty.lower()
        rows.append(
            {
                "key": str(item.get("id") or key),
                "name": name,
                "rarity": rank,
                "attribute": element,
                "specialty": specialty,
                "source": "hakush",
            }
        )
    return rows
