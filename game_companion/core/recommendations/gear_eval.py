"""Gear inventory evaluation (Milestone 11) — deterministic, adapter-driven."""

from __future__ import annotations

from sqlalchemy.orm import Session

from game_companion.core.games.base import GameAdapter
from game_companion.db.models import Character, GearItem
from game_companion.db.repositories import CharacterRepository, GearRepository


def gear_payload(gear: GearItem) -> dict:
    return {
        "slot": gear.slot,
        "set_key": gear.set_key,
        "rarity": gear.rarity,
        "level": gear.level,
        "main_stat_key": gear.main_stat_key,
        "main_stat_value": gear.main_stat_value,
        "substats": gear.substats or [],
    }


def _owned_specialties(session: Session, adapter: GameAdapter, game_id: str, player_id: str) -> list[str]:
    specialties: set[str] = set()
    for char in CharacterRepository(session).search(game_id, player_id, owned=True):
        meta = adapter.character_meta(char.key) or {}
        specialty = char.data.get("specialty") or meta.get("specialty")
        if specialty:
            specialties.add(specialty)
    return sorted(specialties)


def evaluate_gear_item(
    session: Session,
    adapter: GameAdapter,
    game_id: str,
    player_id: str,
    gear: GearItem,
    character: Character | None = None,
) -> dict:
    context: dict = {"owned_specialties": _owned_specialties(session, adapter, game_id, player_id)}
    if character is None and gear.equipped_character_id:
        character = CharacterRepository(session).get(gear.equipped_character_id)
    if character is not None:
        meta = adapter.character_meta(character.key) or {}
        context["character_key"] = character.key
        context["specialty"] = character.data.get("specialty") or meta.get("specialty")
    evaluation = adapter.score_gear(gear_payload(gear), context)
    return {
        "gear_id": gear.id,
        "slot": gear.slot,
        "set_key": gear.set_key,
        "character": character.key if character else None,
        "verdict": evaluation.verdict,
        "score": evaluation.score,
        "score_label": evaluation.label,
        "reasons": evaluation.reasons,
        "components": [
            {
                "name": c.name,
                "value": c.value,
                "max": c.max_value,
                "label": c.label,
                "detail": c.detail,
            }
            for c in evaluation.components
        ],
    }


def evaluate_inventory(
    session: Session,
    adapter: GameAdapter,
    game_id: str,
    player_id: str,
    top_per_character: int = 3,
) -> dict:
    """Whole-inventory view: best pieces per character + discard candidates."""
    gear_repo = GearRepository(session)
    char_repo = CharacterRepository(session)
    characters = [c for c in char_repo.search(game_id, player_id, owned=True)]
    items = gear_repo.search(game_id, player_id)

    per_char: dict[str, list[dict]] = {c.key: [] for c in characters}
    discards: list[dict] = []
    for item in items:
        scored = evaluate_gear_item(session, adapter, game_id, player_id, item)
        entry = {"gear_id": item.id, "slot": item.slot, "set_key": item.set_key,
                 "score": scored["score"], "verdict": scored["verdict"],
                 "equipped": bool(item.equipped_character_id),
                 "locked": item.locked}
        if item.equipped_character_id:
            holder = char_repo.get(item.equipped_character_id)
            entry["equipped_by"] = holder.key if holder else None
        if scored["verdict"] == "likely_safe_to_discard" and not item.equipped_character_id and not item.locked:
            discards.append(entry)
        if item.equipped_character_id:
            continue  # best-for lists consider free pieces only
        for char in characters:
            meta = adapter.character_meta(char.key) or {}
            specialty = char.data.get("specialty") or meta.get("specialty")
            scored_for = evaluate_gear_item(
                session, adapter, game_id, player_id, item,
                character=char if specialty else None,
            )
            per_char[char.key].append(
                {"gear_id": item.id, "slot": item.slot, "score": scored_for["score"],
                 "verdict": scored_for["verdict"]}
            )
    best_for = {
        key: sorted(entries, key=lambda e: (-e["score"], e["gear_id"]))[:top_per_character]
        for key, entries in per_char.items()
    }
    return {
        "best_for": best_for,
        "likely_safe_to_discard": sorted(discards, key=lambda e: e["gear_id"]),
        "note": "All scores are " + adapter.__class__.__name__ + " heuristics, not simulated DPS.",
    }
