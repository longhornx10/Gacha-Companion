"""Account-aware team recommendations (M9) and equipment comparison (M10)."""

from __future__ import annotations

from itertools import combinations
from typing import Any

from sqlalchemy.orm import Session

from game_companion.core.games.base import GameAdapter
from game_companion.core.teams.scoring import score_team_composition
from game_companion.db.models import Character
from game_companion.db.repositories import (
    CharacterRepository,
    EquipmentRepository,
    TeamRepository,
)


def _preferences(session: Session, player_id: str, game_id: str) -> dict[str, Any]:
    from game_companion.db.repositories import PlayerRepository

    prefs: dict[str, Any] = {}
    for p in PlayerRepository(session).list_preferences(player_id):
        if p.scope == "global" or p.scope == game_id:
            prefs[p.key] = p.value
    return prefs


def _encounter_constraints(session: Session, adapter: GameAdapter, game_id: str, encounter: str | None) -> dict:
    if not encounter:
        return {}
    from game_companion.db.repositories import EncounterRepository

    row = EncounterRepository(session).find_by_key(game_id, encounter)
    if row is not None:
        merged: dict[str, Any] = {}
        for slot in row.slots:
            merged.update(slot.constraints or {})
        return merged
    return {}


def recommend_teams(
    session: Session,
    adapter: GameAdapter,
    game_id: str,
    player_id: str,
    *,
    encounter: str | None = None,
    count: int = 5,
) -> dict:
    char_repo = CharacterRepository(session)
    owned = [c for c in char_repo.search(game_id, player_id, owned=True)]
    if len(owned) < adapter.team_rules().min_size:
        term = adapter.terminology()
        return {
            "error": f"need at least {adapter.team_rules().min_size} owned {term.character_plural}",
            "candidates": [],
        }
    keys = [c.key for c in owned]
    team_size = adapter.team_rules().max_size
    constraints = _encounter_constraints(session, adapter, game_id, encounter)
    preferences = _preferences(session, player_id, game_id)

    candidates = sorted(combinations(sorted(keys), team_size))
    if len(candidates) > 120:  # documented deterministic cap for big rosters
        candidates = candidates[:120]

    scored = [
        score_team_composition(
            session, adapter, game_id, player_id, list(combo),
            encounter_constraints=constraints, preferences=preferences,
        )
        for combo in candidates
    ]
    scored.sort(key=lambda s: (-s["total"], s["members"]))

    active_chars = set()
    for team in TeamRepository(session).active_teams(game_id, player_id):
        active_chars |= {m.character_id for m in team.members}
    active_keys = {
        c.key for c in owned if c.id in active_chars
    }

    def _tag(s: dict) -> dict:
        uses_active = active_keys.intersection(s["members"])
        out = dict(s)
        out["overlaps_active_teams"] = sorted(uses_active)
        return out

    best = [_tag(s) for s in scored[:count]]
    comfortable = sorted(
        scored,
        key=lambda s: (-next((c["value"] for c in s["components"] if c["name"] == "comfort"), 0) * 2 - s["total"], s["members"]),
    )[: max(2, count // 2)]
    top_members = set(scored[0]["members"]) if scored else set()
    substitutes = [
        _tag(s)
        for s in scored
        if len(set(s["members"]) & top_members) >= team_size - 1 and s["members"] != list(top_members)
    ][:count]

    return {
        "encounter": encounter,
        "best_owned": best,
        "most_comfortable": [_tag(s) for s in comfortable],
        "substitutes": substitutes,
        "note": "Heuristic scores from adapter rules + stored build readiness. Not simulated DPS.",
    }


def compare_equipment(
    session: Session,
    adapter: GameAdapter,
    game_id: str,
    player_id: str,
    character: Character,
    item_ids: list[str] | None = None,
) -> dict:
    """M10: owned-equipment comparison for one character (theoretical-best vs
    best-owned is distinguished by item ownership — only owned items exist here)."""
    equipment_repo = EquipmentRepository(session)
    items = equipment_repo.search(game_id, player_id)
    if item_ids:
        wanted = set(item_ids)
        items = [i for i in items if i.id in wanted]
    else:
        # Only items usable by this character's game/player (all of them are).
        pass

    scored: list[dict] = []
    equipped_id = None
    for item in items:
        component = adapter.score_equipment_for_character(character.key, {
            "key": item.key, "display_name": item.display_name, "rarity": item.rarity,
            "level": item.level, "refinement": item.refinement,
        })
        holder = item.equipped_character_id
        holder_char = CharacterRepository(session).get(holder) if holder else None
        scored.append({
            "item_id": item.id,
            "display_name": item.display_name,
            "rarity": item.rarity,
            "level": item.level,
            "refinement": item.refinement,
            "equipped_by": holder_char.key if holder_char else None,
            "quality": {
                "value": round(component.value, 2),
                "max": component.max_value,
                "label": component.label,
                "detail": component.detail,
            },
        })
        if holder_char is not None and holder_char.id == character.id:
            equipped_id = item.id

    scored.sort(key=lambda s: (-s["quality"]["value"], s["display_name"]))
    best_owned = scored[0] if scored else None
    easiest_upgrade = None
    if scored:
        def headroom(entry: dict) -> float:
            level_cap = float(adapter.equipment_rules().get("level_cap") or 60)
            level = entry["level"] or 0
            return entry["quality"]["value"] * (level_cap - level) / level_cap

        easiest_upgrade = max(scored, key=lambda e: (headroom(e), e["display_name"]))
    return {
        "character": character.key,
        "currently_equipped": equipped_id,
        "ranking": scored,
        "best_owned": best_owned,
        "easiest_upgrade": easiest_upgrade,
        "note": "Relative heuristic quality only — no DPS percentages are fabricated.",
    }
