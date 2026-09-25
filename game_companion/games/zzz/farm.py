"""ZZZ farm-planner glue (M26): dataset loading, disc grading, scarcity.

Everything game-specific about the planner lives here: the meta dataset
(drive_meta.json), Area Patrol stages, slot pools, and the heuristic quality
model that turns raw inventory rows into credits the generic core math can
consume. Unknowns stay ungraded rather than guessed.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from game_companion.core.farm import service as farm_service
from game_companion.core.farm.service import FarmPlanConfig
from game_companion.games.zzz import gear_rules, resource_rules

# Roman display for disc slots (in-game convention).
SLOT_DISPLAY = {"1": "I", "2": "II", "3": "III", "4": "IV", "5": "V", "6": "VI"}

# Verified in-game mechanic: S-rank discs enhance to +15. Lower rarities cap
# earlier in practice, but exact caps are unverified — the model applies
# HEURISTIC ceilings instead of inventing numbers.
S_RANK_LEVEL_CAP = 15
LEVEL_BANDS: tuple[tuple[int, float], ...] = (
    (15, 1.0),  # finished
    (9, 0.9),   # strong
    (3, 0.75),  # good
    (0, 0.5),   # placeholder
)
RARITY_CREDIT_CAP = {5: 1.0, 4: 0.75, 3: 0.5}  # HEURISTIC ceilings by rank
_RANK_NUMBERS = {"S": 5, "A": 4, "B": 3, 5: 5, 4: 4, 3: 3}


def _rarity_number(rarity: Any) -> int:
    return _RANK_NUMBERS.get(rarity, _RANK_NUMBERS.get(str(rarity).upper(), 3))

# Narrow-pool mains that make a set harder to farm well (HEURISTIC weights,
# configurable here). Slot V elemental bonuses are the rarest useful main;
# crit/utility mains on IV/VI are the next tier.
SCARCITY_BOOSTS = {
    "normal": 1.0,
    "meaningful": 1.2,
    "severe_iv_vi": 1.3,
    "severe_v": 1.5,
}
_ELEMENTAL_MAINS = {
    "physical_dmg", "fire_dmg", "ice_dmg", "electric_dmg", "ether_dmg", "wind_dmg",
}
_SPECIAL_IV_VI_MAINS = {
    "crit_rate", "crit_dmg", "anomaly_proficiency", "anomaly_mastery", "energy_regen", "impact",
}
BETA_CHOICES = (1.0, 1.2, 1.3, 1.5)


def load_drive_meta(overrides_dir: Any = None) -> dict[str, Any]:
    return resource_rules.load_data_json("drive_meta", overrides_dir)


def load_farm_stages(overrides_dir: Any = None) -> dict[str, Any]:
    return resource_rules.load_data_json("farm_stages", overrides_dir)


def grade_disc(gear: Mapping[str, Any]) -> dict[str, Any]:
    """Quality credit for one disc on the planner's 5-step scale (HEURISTIC).

    unusable 0.00 (wrong main for its slot) / placeholder 0.50 / good 0.75 /
    strong 0.90 / finished 1.00. A disc with no set is unranked: it cannot be
    attributed to any set's inventory, so it credits nothing.
    """
    set_key = gear.get("set_key")
    if not set_key:
        return {
            "grade": "unranked",
            "credit": 0.0,
            "reason": "no set recorded — cannot count toward any set's inventory",
        }
    pool = _slot_pool(str(gear.get("slot") or ""))
    main_key = gear.get("main_stat_key")
    if main_key and pool and main_key not in pool:
        return {
            "grade": "unusable",
            "credit": 0.0,
            "reason": f"main stat {main_key} cannot roll in slot {SLOT_DISPLAY.get(str(gear.get('slot')), gear.get('slot'))}",
        }
    if not main_key:
        return {"grade": "placeholder", "credit": 0.5, "reason": "main stat not recorded yet"}

    level = gear.get("level")
    credit = LEVEL_BANDS[-1][1]
    if level is not None:
        for threshold, band_credit in LEVEL_BANDS:
            if level >= threshold:
                credit = band_credit
                break
    else:
        # level unknown: assume unfinished but usable rather than maxed
        credit = 0.5

    cap = RARITY_CREDIT_CAP.get(_rarity_number(gear.get("rarity")), 0.5)
    capped = credit > cap
    credit = min(credit, cap)
    grade = {1.0: "finished", 0.9: "strong", 0.75: "good", 0.5: "placeholder"}[credit]
    return {
        "grade": grade,
        "credit": credit,
        "reason": f"level {level if level is not None else '?'} main {main_key or 'unknown'}"
        + (f" (rarity caps credit at {cap:g})" if capped else ""),
    }


def _slot_pool(slot_key: str) -> tuple[str, ...]:
    for slot in gear_rules.GEAR_SLOTS:
        if slot.key == slot_key:
            return slot.main_stat_pool
    return ()


def scarcity_by_set(units: Sequence[Mapping]) -> dict[str, dict[str, Any]]:
    """Per-set farming-difficulty boost from the mains its users want (HEURISTIC).

    severe_v (1.5): any primary build demands an elemental slot-V main.
    severe_iv_vi (1.3): crit/utility mains demanded on slots IV/VI.
    meaningful (1.2): set is some primary build's target.
    normal (1.0): everything else.
    """
    boost: dict[str, dict[str, Any]] = {}
    for unit in units:
        primary = farm_service.primary_build(unit)
        used = {s for s in (primary.get("four_piece"), primary.get("two_piece")) if s}
        mains = set()
        for slot_groups in (unit.get("slot_mains") or {}).values():
            for group in slot_groups or ():
                mains.update(group)
        for set_key in used:
            entry = boost.setdefault(
                set_key, {"boost": SCARCITY_BOOSTS["normal"], "severity": "normal", "mains": set()}
            )
            entry["mains"].update(mains)
    for entry in boost.values():
        mains = entry["mains"]
        if mains & _ELEMENTAL_MAINS:
            entry["boost"], entry["severity"] = SCARCITY_BOOSTS["severe_v"], "severe_v"
        elif mains & _SPECIAL_IV_VI_MAINS:
            entry["boost"], entry["severity"] = SCARCITY_BOOSTS["severe_iv_vi"], "severe_iv_vi"
        else:
            entry["boost"], entry["severity"] = SCARCITY_BOOSTS["meaningful"], "meaningful"
        entry["mains"] = sorted(entry["mains"])
    return boost


def build_farm_plan(
    adapter: Any,
    gear_rows: Sequence[Mapping],
    beta: float = 1.2,
    unit_keys: Sequence[str] | None = None,
) -> dict[str, Any] | None:
    """Assemble the full labeled plan for this game, or None when the game
    has no meta dataset (the planner stays silent instead of pretending).

    ``unit_keys`` restricts the demand model to the player's own roster
    (character keys; underscore/hyphen spelling is normalized). When none of
    the player's agents are in the meta dataset the plan falls back to the
    full meta and says so (``scope.fallback``).
    """
    meta = load_drive_meta(adapter._overrides_dir)
    stage_doc = load_farm_stages(adapter._overrides_dir)
    all_units = meta.get("agents") or []
    stages = stage_doc.get("stages") or []
    if not all_units or not stages:
        return None

    units = all_units
    scope_fallback = False
    if unit_keys is not None:
        wanted = {str(k).strip().replace("_", "-") for k in unit_keys}
        units = [u for u in all_units if u.get("key") in wanted]
        if not units:
            units, scope_fallback = all_units, True

    set_info = {s["key"]: s for s in adapter.gear_sets()}
    graded: list[dict[str, Any]] = []
    for row in gear_rows:
        if (row.get("gear_type") or "disc") != "disc":
            continue
        graded.append({**dict(row), **grade_disc(row)})

    scarcity = {
        key: entry["boost"] for key, entry in scarcity_by_set(units).items()
    }
    plan = farm_service.build_plan(
        units=units,
        stages=stages,
        set_info=set_info,
        graded_inventory=graded,
        scarcity=scarcity,
        config=FarmPlanConfig(beta=beta),
    )
    plan["scope"] = {
        "requested": unit_keys is not None,
        "agents": len(units),
        "fallback": scope_fallback,
    }

    # Bottleneck slot per set: the slot with the largest shortfall of usable
    # discs against an even share of the target (HEURISTIC — real targets are
    # build-shaped, not even).
    bottlenecks: dict[str, dict[str, Any]] = {}
    by_set: dict[str, list[Mapping]] = {}
    for row in graded:
        if row.get("set_key"):
            by_set.setdefault(row["set_key"], []).append(row)
    for row in plan["set_rows"]:
        rows = by_set.get(row["set_key"], [])
        if not rows:
            bottlenecks[row["set_key"]] = {
                "slot": None, "usable": 0, "expected": None,
                "detail": "no discs recorded yet",
            }
            continue
        usable_by_slot: dict[str, int] = {}
        for r in rows:
            if (r.get("credit") or 0) > 0 and r.get("slot"):
                usable_by_slot[r["slot"]] = usable_by_slot.get(r["slot"], 0) + 1
        expected = row["target"] / 6.0 if row["target"] else 0.0
        worst = None
        if usable_by_slot:
            worst = min(
                usable_by_slot,
                key=lambda s: (usable_by_slot[s] - expected, s),
            )
        bottlenecks[row["set_key"]] = {
            "slot": SLOT_DISPLAY.get(worst, worst) if worst else None,
            "usable": sum(usable_by_slot.values()),
            "expected_per_slot": round(expected, 2),
            "detail": (
                f"shortest on slot {SLOT_DISPLAY.get(worst, worst)} "
                f"({usable_by_slot.get(worst, 0)} usable vs ~{expected:.1f} needed)"
                if worst else "no usable discs yet"
            ),
        }
    plan["bottlenecks"] = bottlenecks

    plan["provenance"] = {
        "meta": meta.get("_meta") or {},
        "stages": stage_doc.get("_meta") or {},
        "sets": (set_info.get("_meta") if isinstance(set_info.get("_meta"), dict) else None),
        "grading": {
            "label": farm_service.LABEL_HEURISTIC,
            "scale": {
                "unusable": 0.0, "placeholder": 0.5, "good": 0.75,
                "strong": 0.9, "finished": 1.0,
            },
            "notes": [
                "S-rank enhance cap +15 is a VERIFIED MECHANIC; lower-rarity credit "
                "ceilings (A 0.75, B 0.5) are HEURISTIC (exact caps unverified)",
                "equipped discs count toward set inventory; equipped/unequipped is "
                "reported separately for context",
            ],
        },
        "scarcity": {
            "label": farm_service.LABEL_HEURISTIC,
            "table": SCARCITY_BOOSTS,
        },
    }
    plan["scarcity_detail"] = {
        key: {"severity": entry["severity"], "mains": entry["mains"]}
        for key, entry in scarcity_by_set(units).items()
    }
    plan["beta_choices"] = list(BETA_CHOICES)
    plan["stage_index"] = [
        {"key": s.get("key"), "name": s.get("name"), "battery_cost": s.get("battery_cost")}
        for s in stages
    ]
    equipped = sum(1 for r in graded if r.get("equipped_character_id"))
    plan["inventory_summary"] = {
        "discs": len(graded),
        "equipped": equipped,
        "unequipped": len(graded) - equipped,
        "graded_out": sum(1 for r in graded if r.get("grade") == "unusable"),
    }
    return plan
