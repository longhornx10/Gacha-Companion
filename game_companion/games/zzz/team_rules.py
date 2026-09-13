"""ZZZ team rules and heuristic scoring (all components labeled HEURISTIC)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from game_companion.core.games.base import (
    LABEL_HEURISTIC,
    ScoreComponent,
    TeamRules,
)


def score_team(
    member_keys: Sequence[str], meta_lookup, context: Mapping[str, Any]
) -> list[ScoreComponent]:
    """Heuristic ZZZ team components. No DPS is claimed anywhere."""
    metas = [meta_lookup(k) or {} for k in member_keys]
    specialties = [m.get("specialty") for m in metas]
    attributes = [m.get("attribute") for m in metas]
    factions = [m.get("faction") for m in metas if m.get("faction")]

    # Role balance: ZZZ teams generally want a main damage dealer, and benefit
    # from stun/anomaly setup plus support/defense utility.
    has_damage = any(s in ("attack", "anomaly") for s in specialties)
    has_setup = any(s in ("stun", "anomaly") for s in specialties)
    has_utility = any(s in ("support", "defense") for s in specialties)
    role_score = (4 if has_damage else 0) + (3 if has_setup else 0) + (3 if has_utility else 0)
    role_detail = (
        f"damage={'yes' if has_damage else 'no'}, setup(stun/anomaly)="
        f"{'yes' if has_setup else 'no'}, utility(support/defense)={'yes' if has_utility else 'no'}"
    )

    # Faction pairing (Additional Ability often keys off faction pairs) — heuristic.
    faction_pairs = len(factions) - len(set(factions)) if factions else 0
    faction_score = 8.0 if faction_pairs >= 1 else 4.0
    faction_detail = (
        "contains at least one faction pair (heuristic Additional Ability proxy)"
        if faction_pairs >= 1
        else "no faction pair — Additional Ability may still trigger via other conditions"
    )

    distinct_attributes = len({a for a in attributes if a})
    attribute_score = min(10.0, distinct_attributes * 10 / 3)
    attribute_detail = f"{distinct_attributes} distinct attribute(s) among {len(member_keys)} members"

    components = [
        ScoreComponent("role_balance", role_score, 10, LABEL_HEURISTIC, role_detail),
        ScoreComponent("faction_synergy", faction_score, 10, LABEL_HEURISTIC, faction_detail),
        ScoreComponent("attribute_diversity", attribute_score, 10, LABEL_HEURISTIC, attribute_detail),
    ]

    prefs = context.get("preferences") or {}
    if prefs.get("values_comfort_over_dps"):
        comfortable = has_utility and not _is_double_anomaly(specialties)
        components.append(
            ScoreComponent(
                "comfort",
                8.0 if comfortable else 4.0,
                10,
                LABEL_HEURISTIC,
                "comfort preference: utility member present, no demanding double-anomaly setup"
                if comfortable
                else "comfort preference: demanding composition for this player",
            )
        )
    return components


def _is_double_anomaly(specialties: Sequence[str | None]) -> bool:
    return sum(1 for s in specialties if s == "anomaly") >= 2


def character_slot_fit(
    character_key: str, constraints: Mapping[str, Any], meta_lookup
) -> float:
    """0..10 individual fit for an encounter slot (heuristic)."""
    meta = meta_lookup(character_key) or {}
    score = 5.0
    preferred_attributes = constraints.get("preferred_attributes") or []
    preferred_specialties = constraints.get("preferred_specialties") or []
    if meta.get("attribute") and meta["attribute"] in preferred_attributes:
        score += 2.5
    if meta.get("specialty") and meta["specialty"] in preferred_specialties:
        score += 2.5
    return max(0.0, min(10.0, score))


TEAM_RULES = TeamRules(min_size=3, max_size=3)
