"""Team scoring with visible components (Milestone 16).

Every score is a weighted sum of explicit, labeled components
(HEURISTIC/MEASURED/CONSENSUS). Nothing is presented as simulated DPS.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from itertools import combinations
from typing import Any

from sqlalchemy.orm import Session

from game_companion.core.games.base import LABEL_HEURISTIC, GameAdapter, ScoreComponent
from game_companion.db.models import Character
from game_companion.db.repositories import (
    BuildRepository,
    CharacterRepository,
    EquipmentRepository,
)

# Component weights for the total. Kept explicit and simple on purpose.
WEIGHTS = {
    "synergy": 0.35,
    "encounter_fit": 0.30,
    "build_readiness": 0.20,
    "comfort": 0.15,
}


def build_readiness(session: Session, adapter: GameAdapter, char: Character) -> ScoreComponent:
    """0..10: does the character have an active build, equipment and filled gear?"""
    builds = BuildRepository(session)
    gear_slots_count = max(len(adapter.gear_slots()), 1)
    active = builds.active_for_character(char.id)
    detail_bits = []
    value = 2.0  # owned at all
    if active is None:
        detail_bits.append("no active build")
    else:
        detail_bits.append("active build")
        value += 2.0
        equipment = (
            EquipmentRepository(session).get(active.equipment_item_id)
            if active.equipment_item_id
            else None
        )
        if equipment is not None:
            value += 2.0
            detail_bits.append(f"equipment lv {equipment.level if equipment.level is not None else '?'}")
        else:
            detail_bits.append("no equipment")
        filled = sum(1 for row in active.gear_slots if row.gear_item_id)
        value += 4.0 * (filled / gear_slots_count)
        detail_bits.append(f"gear {filled}/{gear_slots_count}")
    return ScoreComponent("build_readiness", min(10.0, value), 10, LABEL_HEURISTIC, "; ".join(detail_bits))


def comfort_score(preferences: Mapping[str, Any], member_keys: Sequence[str], adapter: GameAdapter) -> ScoreComponent:
    value = 5.0
    details = []
    if preferences.get("prefers_simple_rotations"):
        value += 2.0
        details.append("prefers simple rotations")
    if preferences.get("dislikes_high_execution_teams"):
        value -= 2.0
        details.append("dislikes high-execution teams")
    if preferences.get("values_comfort_over_dps"):
        value += 1.0
        details.append("comfort prioritized")
    return ScoreComponent("comfort", max(0.0, min(10.0, value)), 10, LABEL_HEURISTIC, "; ".join(details) or "neutral preferences")


def score_team_composition(
    session: Session,
    adapter: GameAdapter,
    game_id: str,
    player_id: str,
    member_keys: Sequence[str],
    *,
    encounter_constraints: Mapping[str, Any] | None = None,
    preferences: Mapping[str, Any] | None = None,
    comfort_weight: float = 1.0,
) -> dict:
    preferences = preferences or {}
    char_repo = CharacterRepository(session)
    characters: dict[str, Character] = {}
    for key in member_keys:
        char = char_repo.get_by_key_or_raise(game_id, player_id, key)
        characters[key] = char

    synergy_components = adapter.score_team(
        member_keys, {"preferences": preferences, "game_id": game_id}
    )
    synergy_avg = sum(c.value for c in synergy_components) / max(len(synergy_components), 1)

    readiness = [build_readiness(session, adapter, c) for c in characters.values()]
    readiness_avg = sum(c.value for c in readiness) / max(len(readiness), 1)

    components = list(synergy_components) + readiness
    if encounter_constraints:
        fits = [
            adapter.character_slot_fit(key, encounter_constraints) for key in member_keys
        ]
        fit_avg = sum(fits) / max(len(fits), 1)
        components.append(
            ScoreComponent(
                "encounter_fit",
                fit_avg,
                10,
                LABEL_HEURISTIC,
                "average per-character slot fit from adapter rules",
            )
        )
        encounter_fit = fit_avg
    else:
        encounter_fit = 5.0
        components.append(
            ScoreComponent("encounter_fit", 5.0, 10, LABEL_HEURISTIC, "no encounter constraints given; neutral")
        )

    comfort = comfort_score(preferences, member_keys, adapter)
    if comfort_weight > 0:
        components.append(comfort)

    total = (
        WEIGHTS["synergy"] * synergy_avg
        + WEIGHTS["encounter_fit"] * encounter_fit
        + WEIGHTS["build_readiness"] * readiness_avg
        + WEIGHTS["comfort"] * comfort.value * comfort_weight
    ) / (WEIGHTS["synergy"] + WEIGHTS["encounter_fit"] + WEIGHTS["build_readiness"] + WEIGHTS["comfort"] * comfort_weight)

    return {
        "members": list(member_keys),
        "total": round(total, 2),
        "total_label": LABEL_HEURISTIC,
        "components": [
            {
                "name": c.name,
                "value": round(c.value, 2),
                "max": c.max_value,
                "label": c.label,
                "detail": c.detail,
            }
            for c in components
        ],
    }


def viable_member_keys(session: Session, game_id: str, player_id: str) -> list[str]:
    return [
        c.key for c in CharacterRepository(session).search(game_id, player_id, owned=True)
    ]


def enumerate_candidate_teams(
    member_keys: Sequence[str], team_size: int, max_candidates: int = 120
) -> list[tuple[str, ...]]:
    """Deterministic candidate enumeration with a deterministic size cap."""
    keys = sorted(member_keys)
    if len(keys) <= 10:
        return sorted(combinations(keys, team_size))
    # Deterministic pre-ranking for big rosters: alphabetical is deterministic
    # but arbitrary; better: enumerate combinations over the full set only if
    # it stays small, else take the first 10 sorted keys (documented fallback).
    combos = sorted(combinations(keys, team_size))
    if len(combos) <= max_candidates:
        return combos
    return combos[:max_candidates]
