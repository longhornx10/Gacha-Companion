"""Generic gear-farming planner math (M26).

Answers, for any set-based gear system: "which set should I farm next?"
from demand-weighted meta data, a physical-need baseline, and the player's
actual inventory quality. Pure arithmetic over plain dicts — every game fact
(set names, stages, builds, grades) arrives via the adapter. Inputs are
labeled at the edges; unknowns stay unknown, assumptions stay explicit.

Core equations (per gear set s):
  demand   D_s  = Σ_units Σ_variants q_v × pieces_v(s)          (pieces: 4 / 2)
  need     P_s  = #units whose primary (highest-q) build uses s (once per unit)
  target   T_s  = ceil(beta × P_s)                               (beta: player setting)
  coverage C_s  = effective_s / T_s            (clamped display 0..1+; 0 when T=0)
  pressure F_s  = demand_share_s × max(0, 1 − C_s) × scarcity_s
  stage    F_n  = Σ_{s in n} F_s × split(s at n)               (split: drop-share)

All labels: DEMAND/NEED derive from CURRENT BUILD DATA; TARGET carries the
beta HEURISTIC; EFFECTIVE applies HEURISTIC grading to inventory; the stage
split is an ASSUMPTION unless the adapter supplies learned rates.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

LABEL_CURRENT_BUILD_DATA = "CURRENT BUILD DATA"
LABEL_DERIVED = "DERIVED RESULT"
LABEL_HEURISTIC = "HEURISTIC"
LABEL_ASSUMPTION = "ASSUMPTION"
LABEL_VERIFIED = "VERIFIED MECHANIC"
LABEL_UNKNOWN = "UNKNOWN-NEEDS DATA"


@dataclass(frozen=True)
class FarmPlanConfig:
    """Player-tunable planner knobs. Every field is a documented heuristic."""

    beta: float = 1.2
    # ASSUMPTION: a stage's drop pool splits evenly between its sets until
    # learned otherwise (no official drop rates published).
    stage_split: float = 0.5
    # Keep total pressure dimensionless; stage costs surface in the UI only.
    min_pressure_rows: int = 1


def meta_demand(units: Sequence[Mapping]) -> dict[str, float]:
    """D_s: demand-weighted pieces wanted per set across the meta units.

    Each unit contributes its variants: q sums to 1 per unit, so a unit asks
    for exactly 4 four-piece units + 2 two-piece units in expectation — not
    6 of every set it might use.
    """
    demand: dict[str, float] = {}
    for unit in units:
        for variant in unit.get("build_variants") or ():
            q = float(variant.get("q") or 0.0)
            if q <= 0:
                continue
            four = variant.get("four_piece")
            two = variant.get("two_piece")
            if four:
                demand[four] = demand.get(four, 0.0) + 4.0 * q
            if two:
                demand[two] = demand.get(two, 0.0) + 2.0 * q
    return demand


def primary_build(unit: Mapping) -> Mapping:
    """The unit's highest-weighted variant; falls back to an empty build."""
    variants = unit.get("build_variants") or ()
    if not variants:
        return {}
    return max(variants, key=lambda v: float(v.get("q") or 0.0))


def physical_need(units: Sequence[Mapping]) -> dict[str, int]:
    """P_s: how many meta units' primary builds use s (each unit counts once)."""
    need: dict[str, int] = {}
    for unit in units:
        build = primary_build(unit)
        for set_key in (build.get("four_piece"), build.get("two_piece")):
            if set_key:
                need[set_key] = need.get(set_key, 0) + 1
    return need


def targets(need: Mapping[str, int], beta: float) -> dict[str, int]:
    """T_s = ceil(beta × P_s)."""
    return {set_key: math.ceil(beta * count) for set_key, count in need.items()}


def effective_inventory(graded_rows: Sequence[Mapping]) -> dict[str, float]:
    """I_s_eff: Σ quality credits per set, from pre-graded inventory rows."""
    effective: dict[str, float] = {}
    for row in graded_rows:
        set_key = row.get("set_key")
        if not set_key:
            continue
        effective[set_key] = effective.get(set_key, 0.0) + float(row.get("credit") or 0.0)
    return effective


def coverage(target: Mapping[str, int], effective: Mapping[str, float]) -> dict[str, float | None]:
    """C_s = I_s_eff / T_s; None where no target exists (set outside the meta)."""
    result: dict[str, float | None] = {}
    for set_key, t in target.items():
        result[set_key] = (effective.get(set_key, 0.0) / t) if t > 0 else None
    return result


def farm_pressure(
    demand: Mapping[str, float],
    coverage: Mapping[str, float | None],
    scarcity: Mapping[str, float],
) -> dict[str, float]:
    """F_s = demand_share_s × max(0, 1 − C_s) × scarcity_s.

    Uncovered sets (coverage None) use the full shortfall term (1.0).
    """
    total = sum(v for v in demand.values() if v > 0)
    pressure: dict[str, float] = {}
    for set_key, d in demand.items():
        share = (d / total) if total > 0 else 0.0
        c = coverage.get(set_key)
        shortfall = 1.0 if c is None else max(0.0, 1.0 - c)
        pressure[set_key] = share * shortfall * float(scarcity.get(set_key, 1.0))
    return pressure


def stage_pressure(
    pressure: Mapping[str, float],
    stages: Sequence[Mapping],
    split: float = 0.5,
) -> list[dict]:
    """F_n = Σ_{s in stage} F_s × split(s at n); ranked descending.

    ``split`` applies the same share to every set in a stage (equal-split
    ASSUMPTION). A stage's total achievable pressure is scaled by the number
    of sets it carries; stages the player cannot target (no pressure on their
    sets) naturally sink.
    """
    rows = []
    for stage in stages:
        sets_in_stage = [s for s in stage.get("sets") or () if s in pressure]
        total = sum(pressure.get(s, 0.0) for s in sets_in_stage) * split
        rows.append({
            "stage_key": stage.get("key"),
            "stage_name": stage.get("name"),
            "order": stage.get("order"),
            "sets": list(sets_in_stage),
            "battery_cost": stage.get("battery_cost"),
            "pressure": round(total, 5),
        })
    rows.sort(key=lambda r: (-r["pressure"], r.get("order") or 0))
    return rows


def build_plan(
    units: Sequence[Mapping],
    stages: Sequence[Mapping],
    set_info: Mapping[str, Mapping],
    graded_inventory: Sequence[Mapping],
    scarcity: Mapping[str, float],
    config: FarmPlanConfig | None = None,
) -> dict:
    """One labeled planning payload combining every equation above.

    ``set_info`` maps set_key -> {name?, farmable?, farm_stage?}; anything the
    adapter does not know stays absent rather than guessed.
    """
    cfg = config or FarmPlanConfig()
    demand = meta_demand(units)
    need = physical_need(units)
    target = targets(need, cfg.beta)
    effective = effective_inventory(graded_inventory)
    cover = coverage(target, effective)
    pressure = farm_pressure(demand, cover, scarcity)

    total_d = sum(v for v in demand.values() if v > 0)
    rows = []
    for set_key in sorted(demand, key=lambda k: (-demand[k], k)):
        info = set_info.get(set_key) or {}
        t = target.get(set_key, 0)
        eff = effective.get(set_key, 0.0)
        c = cover.get(set_key)
        stage_key = info.get("farm_stage")
        farmable = bool(info.get("farmable"))
        rows.append({
            "set_key": set_key,
            "set_name": info.get("name") or set_key,
            "demand": round(demand[set_key], 3),
            "demand_share": round(demand[set_key] / total_d, 4) if total_d else 0.0,
            "need": need.get(set_key, 0),
            "target": t,
            "effective": round(eff, 2),
            "coverage": None if c is None else round(c, 3),
            "pressure": round(pressure.get(set_key, 0.0), 5),
            "scarcity": scarcity.get(set_key, 1.0),
            "farmable": farmable,
            "farm_stage": stage_key,
            "in_meta": set_key in target,
        })

    stage_rows = [
        r for r in stage_pressure(pressure, stages, cfg.stage_split)
        if r["pressure"] > 0
    ]
    for stage_row in stage_rows:
        names = [set_info.get(s, {}).get("name") or s for s in stage_row["sets"]]
        stage_row["set_names"] = names
        stage_row["bottleneck_set"] = max(
            stage_row["sets"], key=lambda s: pressure.get(s, 0.0)
        ) if stage_row["sets"] else None
        stage_row["bottleneck_set_name"] = (
            set_info.get(stage_row["bottleneck_set"], {}).get("name")
            or stage_row["bottleneck_set"]
        ) if stage_row["bottleneck_set"] else None

    return {
        "config": {
            "beta": cfg.beta,
            "stage_split": cfg.stage_split,
            "split_label": LABEL_ASSUMPTION,
        },
        "set_rows": rows,
        "stage_rows": stage_rows,
        "labels": {
            "demand": LABEL_CURRENT_BUILD_DATA,
            "need": LABEL_CURRENT_BUILD_DATA,
            "target": LABEL_HEURISTIC,
            "effective": LABEL_HEURISTIC,
            "coverage": LABEL_DERIVED,
            "pressure": LABEL_DERIVED,
            "stage_split": LABEL_ASSUMPTION,
        },
    }
