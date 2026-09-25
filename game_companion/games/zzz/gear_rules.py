"""ZZZ gear rules: Drive Disc slots, main-stat pools, heuristic scoring."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from game_companion.core.games.base import (
    GEAR_VERDICTS,
    LABEL_HEURISTIC,
    GearEvaluation,
    GearSlotDefinition,
    ScoreComponent,
)

# Slot main-stat pools are a VERIFIED MECHANIC (v3.2): slots 1-3 are fixed
# (flat HP / ATK / DEF); slot 4 can roll CRIT stats; slot 5 carries elemental
# damage bonuses; slot 6 carries utility mains. Elemental list includes
# wind_dmg, seen in Prydwen build data (3.2) — flagged UNKNOWN-NEEDS DATA
# until corroborated in-game.
GEAR_SLOTS = [
    GearSlotDefinition(key="1", name="Slot 1", main_stat_pool=("hp",)),
    GearSlotDefinition(key="2", name="Slot 2", main_stat_pool=("atk",)),
    GearSlotDefinition(key="3", name="Slot 3", main_stat_pool=("def",)),
    GearSlotDefinition(
        key="4",
        name="Slot 4",
        main_stat_pool=(
            "hp_pct", "atk_pct", "def_pct", "crit_rate", "crit_dmg", "anomaly_proficiency",
        ),
    ),
    GearSlotDefinition(
        key="5",
        name="Slot 5",
        main_stat_pool=(
            "hp_pct", "atk_pct", "def_pct", "pen_ratio",
            "physical_dmg", "fire_dmg", "ice_dmg", "electric_dmg", "ether_dmg", "wind_dmg",
        ),
    ),
    GearSlotDefinition(
        key="6",
        name="Slot 6",
        main_stat_pool=(
            "hp_pct", "atk_pct", "def_pct", "anomaly_mastery", "energy_regen", "impact",
        ),
    ),
]

# Approximate reference maxima used ONLY to normalize the heuristic score.
# These are not verified game constants; they just scale substat contributions.
SUBSTAT_REFERENCE_MAX: dict[str, float] = {
    "crit_rate": 0.24,
    "crit_dmg": 0.48,
    "atk_pct": 0.30,
    "hp_pct": 0.30,
    "def_pct": 0.48,
    "pen_ratio": 0.24,
    "energy_regen": 0.60,
    "anomaly_proficiency": 12.0,
    "anomaly_mastery": 0.30,
    "atk": 30.0,
    "hp": 112.0,
    "def": 15.0,
    "impact": 0.18,
}

ARCHETYPE_WEIGHTS: dict[str, dict[str, float]] = {
    "attack": {"crit_rate": 0.28, "crit_dmg": 0.28, "atk_pct": 0.22, "pen_ratio": 0.12, "atk": 0.10},
    "anomaly": {
        "anomaly_proficiency": 0.35,
        "anomaly_mastery": 0.20,
        "atk_pct": 0.20,
        "pen_ratio": 0.10,
        "energy_regen": 0.15,
    },
    "stun": {"impact": 0.40, "energy_regen": 0.20, "crit_rate": 0.15, "def_pct": 0.15, "hp_pct": 0.10},
    "support": {
        "energy_regen": 0.30,
        "anomaly_proficiency": 0.25,
        "hp_pct": 0.15,
        "def_pct": 0.15,
        "atk_pct": 0.10,
        "crit_rate": 0.05,
    },
    "defense": {"hp_pct": 0.30, "def_pct": 0.30, "impact": 0.15, "energy_regen": 0.15, "crit_rate": 0.10},
}


def _archetype_score(
    gear: Mapping[str, Any], specialty: str, reasons: list[str]
) -> tuple[float, float, list[str]]:
    """Returns (score_0_100, main_fit, sub_notes) scored against one archetype."""
    weights = ARCHETYPE_WEIGHTS.get(specialty, ARCHETYPE_WEIGHTS["attack"])
    main_stat_key = gear.get("main_stat_key")
    main_fit = 0.0
    local_reasons: list[str] = []
    if main_stat_key:
        if main_stat_key in weights and weights[main_stat_key] >= 0.15:
            main_fit = 1.0
            local_reasons.append(
                f"main stat {main_stat_key} is a top desire for the {specialty} archetype"
            )
        elif main_stat_key in weights:
            main_fit = 0.6
            local_reasons.append(f"main stat {main_stat_key} is usable for the {specialty} archetype")
        else:
            local_reasons.append(f"main stat {main_stat_key} is not valued for the {specialty} archetype")
    else:
        local_reasons.append("main stat unknown")

    sub_score = 0.0
    sub_notes: list[str] = []
    for sub in gear.get("substats") or []:
        key = sub.get("key")
        value = sub.get("value")
        if not key or value is None:
            continue
        weight = weights.get(key, 0.0)
        ref_max = SUBSTAT_REFERENCE_MAX.get(key)
        if weight <= 0 or not ref_max:
            sub_notes.append(f"{key} not weighted for {specialty}")
            continue
        sub_score += weight * min(float(value) / ref_max, 1.0)
        sub_notes.append(f"{key} {value:g}")
    score = 100 * (0.45 * main_fit + 0.55 * min(sub_score, 1.0))
    return score, main_fit, local_reasons + (["substats considered: " + ", ".join(sub_notes)] if sub_notes else [])


def score_gear(gear: Mapping[str, Any], context: Mapping[str, Any], meta_lookup) -> GearEvaluation:
    """Heuristic Drive Disc evaluation with explicit reasons (never a black box).

    If the caller names a character/specialty, the disc is scored for that
    archetype. Otherwise it is scored against its BEST-fit archetype; when that
    best fit is an archetype the player does not own, the verdict becomes
    ``speculative`` (good piece, wrong roster).
    """
    gear = dict(gear)
    character_key = context.get("character_key")
    meta = (meta_lookup(character_key) if character_key else None) or {}
    explicit_specialty = context.get("specialty") or meta.get("specialty")
    owned_specialties = context.get("owned_specialties")

    if explicit_specialty:
        score, main_fit, reasons = _archetype_score(gear, explicit_specialty, [])
        specialty = explicit_specialty
    else:
        scored_archetypes = {
            name: _archetype_score(gear, name, [])[0] for name in ARCHETYPE_WEIGHTS
        }
        specialty = max(sorted(scored_archetypes), key=lambda k: scored_archetypes[k])
        score, main_fit, reasons = _archetype_score(gear, specialty, [])
        reasons.append(f"no target character given — scored against best-fit archetype '{specialty}'")

    verdict: str | None = None
    if not explicit_specialty and isinstance(owned_specialties, list) and owned_specialties:
        if specialty not in owned_specialties and score >= 40:
            verdict = "speculative"
            reasons.append(
                f"good rolls for {specialty}, but you own no {specialty}-archetype character yet"
            )
    score = round(score, 1)

    if verdict is None:
        if score >= 75:
            verdict = "strong"
        elif score >= 55:
            verdict = "useful"
        elif score >= 40:
            verdict = "niche"
        elif score <= 18:
            verdict = "likely_safe_to_discard"
        else:
            verdict = "weak"

    components = [
        ScoreComponent("main_stat_fit", main_fit, 1, LABEL_HEURISTIC),
        ScoreComponent("desired_substats", min(_subscore(gear, specialty), 1.0), 1, LABEL_HEURISTIC),
    ]
    return GearEvaluation(
        verdict=verdict if verdict in GEAR_VERDICTS else "useful",
        score=float(score),
        reasons=[r for r in reasons if r],
        components=components,
    )


def _subscore(gear: Mapping[str, Any], specialty: str) -> float:
    weights = ARCHETYPE_WEIGHTS.get(specialty, ARCHETYPE_WEIGHTS["attack"])
    total = 0.0
    for sub in gear.get("substats") or []:
        key = sub.get("key")
        value = sub.get("value")
        ref_max = SUBSTAT_REFERENCE_MAX.get(key or "")
        if not key or value is None or not ref_max:
            continue
        total += weights.get(key, 0.0) * min(float(value) / ref_max, 1.0)
    return total


def set_bonuses_summary(sets: list[dict], gear: Mapping[str, Any]) -> str:
    """Human hint about which sets a disc belongs to (no fabricated effects)."""
    return gear.get("set_key") or "unknown-set"
