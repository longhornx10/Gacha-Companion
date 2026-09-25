"""M26 farm planner: generic core math, ZZZ grading, dataset invariants."""

from __future__ import annotations

import math

import pytest

from game_companion.core.farm import service as farm
from game_companion.games.zzz import farm as zzz_farm
from game_companion.games.zzz import gear_rules

# ----------------------------------------------------------------- core math

def _unit(key: str, variants: list[dict], slot_mains: dict | None = None) -> dict:
    return {"key": key, "build_variants": variants, "slot_mains": slot_mains or {}}


def test_meta_demand_weights_alternatives_not_every_set_equally():
    units = [
        _unit("a", [{"four_piece": "s4", "two_piece": "t1", "q": 1.0}]),
        _unit("b", [
            {"four_piece": "s4", "two_piece": "t1", "q": 0.5},
            {"four_piece": "s4", "two_piece": "t2", "q": 0.5},
        ]),
    ]
    demand = farm.meta_demand(units)
    # unit a: 4×s4 + 2×t1; unit b: 4×s4 + 1×t1 + 1×t2 (in expectation)
    assert demand["s4"] == pytest.approx(8.0)
    assert demand["t1"] == pytest.approx(3.0)
    assert demand["t2"] == pytest.approx(1.0)


def test_meta_demand_ignores_flexible_two_piece():
    units = [_unit("a", [{"four_piece": "s4", "two_piece": None, "q": 1.0}])]
    demand = farm.meta_demand(units)
    assert demand == {"s4": pytest.approx(4.0)}


def test_physical_need_counts_each_unit_once():
    units = [
        _unit("a", [{"four_piece": "s4", "two_piece": "t1", "q": 1.0}]),
        _unit("b", [
            {"four_piece": "s4", "two_piece": "t2", "q": 0.6},
            {"four_piece": "s4", "two_piece": "t1", "q": 0.4},
        ]),
    ]
    need = farm.physical_need(units)
    # only each unit's primary (highest-q) build counts, once per unit:
    # b's alternative 2pc (t1 at 0.4) adds nothing on top of its primary
    assert need == {"s4": 2, "t1": 1, "t2": 1}


def test_targets_round_up_with_beta():
    assert farm.targets({"x": 3, "y": 0}, 1.2) == {"x": 4, "y": 0}


def test_coverage_none_without_target():
    assert farm.coverage({"x": 2}, {"x": 1.0}) == {"x": 0.5}
    assert farm.coverage({"x": 0}, {"x": 1.0}) == {"x": None}


def test_farm_pressure_orders_uncovered_heavy_demand_first():
    demand = {"hot": 6.0, "cold": 2.0}
    cover = {"hot": 0.0, "cold": 1.0}
    scarcity = {"hot": 1.5, "cold": 1.5}
    pressure = farm.farm_pressure(demand, cover, scarcity)
    # hot: (6/8)×1×1.5 = 1.125; cold: (2/8)×0×1.5 = 0
    assert pressure["hot"] == pytest.approx(1.125)
    assert pressure["cold"] == 0.0


def test_farm_pressure_full_shortfall_when_set_has_no_target():
    demand = {"only": 4.0}
    pressure = farm.farm_pressure(demand, {}, {})
    assert pressure["only"] == pytest.approx(1.0)


def test_stage_pressure_splits_evenly_and_ranks():
    stages = [
        {"key": "n1", "name": "One", "order": 1, "sets": ["a", "b"], "battery_cost": 60},
        {"key": "n2", "name": "Two", "order": 2, "sets": ["c", "d"], "battery_cost": 60},
    ]
    pressure = {"a": 0.4, "b": 0.1, "c": 0.2, "d": 0.0}
    rows = farm.stage_pressure(pressure, stages, split=0.5)
    assert rows[0]["stage_key"] == "n1"
    assert rows[0]["pressure"] == pytest.approx(0.25)
    assert rows[1]["pressure"] == pytest.approx(0.1)
    assert all(r["pressure"] > 0 for r in rows)


def test_build_plan_payload_is_labeled():
    units = [_unit("a", [{"four_piece": "s4", "two_piece": "t1", "q": 1.0}])]
    stages = [{"key": "n1", "name": "One", "sets": ["s4", "t1"], "battery_cost": 60}]
    set_info = {"s4": {"name": "Set Four", "farmable": True, "farm_stage": "n1"},
                "t1": {"name": "Tee One", "farmable": True, "farm_stage": "n1"}}
    plan = farm.build_plan(
        units=units, stages=stages, set_info=set_info,
        graded_inventory=[{"set_key": "s4", "credit": 1.0}],
        scarcity={"s4": 1.2, "t1": 1.2},
        config=farm.FarmPlanConfig(beta=1.2),
    )
    rows = {r["set_key"]: r for r in plan["set_rows"]}
    assert rows["s4"]["target"] == math.ceil(1.2 * 1)
    assert rows["s4"]["effective"] == 1.0
    assert rows["t1"]["effective"] == 0.0
    assert plan["labels"]["demand"] == "CURRENT BUILD DATA"
    assert plan["labels"]["stage_split"] == "ASSUMPTION"
    assert plan["stage_rows"][0]["stage_name"] == "One"


# ------------------------------------------------------------- ZZZ grading

def test_grade_disc_wrong_main_for_slot_is_unusable():
    grade = zzz_farm.grade_disc({
        "set_key": "woodpecker_electro", "slot": "4",
        "main_stat_key": "impact", "rarity": 5, "level": 15,
    })
    assert grade["grade"] == "unusable"
    assert grade["credit"] == 0.0


def test_grade_disc_maxed_s_rank_is_finished():
    grade = zzz_farm.grade_disc({
        "set_key": "woodpecker_electro", "slot": "4",
        "main_stat_key": "crit_rate", "rarity": 5, "level": 15,
    })
    assert grade == {"grade": "finished", "credit": 1.0, "reason": grade["reason"]}


def test_grade_disc_a_rank_caps_at_good():
    grade = zzz_farm.grade_disc({
        "set_key": "woodpecker_electro", "slot": "4",
        "main_stat_key": "crit_rate", "rarity": 4, "level": 15,
    })
    assert grade["grade"] == "good"
    assert grade["credit"] == 0.75
    assert "rarity caps" in grade["reason"]


def test_grade_disc_low_level_is_placeholder():
    grade = zzz_farm.grade_disc({
        "set_key": "woodpecker_electro", "slot": "6",
        "main_stat_key": "energy_regen", "rarity": 5, "level": 0,
    })
    assert grade["grade"] == "placeholder"
    assert grade["credit"] == 0.5


def test_grade_disc_unknown_set_is_unranked():
    grade = zzz_farm.grade_disc({"slot": "4", "main_stat_key": "crit_rate"})
    assert grade["grade"] == "unranked"
    assert grade["credit"] == 0.0


def test_grade_disc_unknown_main_is_placeholder():
    grade = zzz_farm.grade_disc({"set_key": "woodpecker_electro", "slot": "4", "rarity": 5})
    assert grade["grade"] == "placeholder"


def test_grade_disc_elemental_slot5_mains_are_valid():
    grade = zzz_farm.grade_disc({
        "set_key": "fanged_metal", "slot": "5",
        "main_stat_key": "physical_dmg", "rarity": 5, "level": 9,
    })
    assert grade["grade"] == "strong"


# ------------------------------------------------- dataset invariants (ZZZ)

@pytest.fixture(scope="module")
def zzz_datasets():
    from game_companion.core.games.registry import get_adapter

    adapter = get_adapter("zzz")
    meta = zzz_farm.load_drive_meta(adapter._overrides_dir)
    stages = zzz_farm.load_farm_stages(adapter._overrides_dir)
    sets = {s["key"]: s for s in adapter.gear_sets()}
    return meta, stages, sets


def test_datasets_carry_provenance(zzz_datasets):
    meta, stages, _ = zzz_datasets
    for doc in (meta["_meta"], stages["_meta"]):
        assert doc["label"] == "CURRENT BUILD DATA"
        assert doc["patch"]
        assert doc["retrieved"]
        assert doc.get("source") or doc.get("sources")


def test_meta_units_have_normalized_weights(zzz_datasets):
    meta, _, sets = zzz_datasets
    units = meta["agents"]
    assert len(units) >= 40
    for unit in units:
        variants = unit["build_variants"]
        assert variants, unit["key"]
        total = sum(v["q"] for v in variants)
        assert total == pytest.approx(1.0, abs=0.01), unit["key"]
        four_sums: dict[str, float] = {}
        for v in variants:
            assert v["four_piece"] in sets, (unit["key"], v["four_piece"])
            if v["two_piece"]:
                assert v["two_piece"] in sets, (unit["key"], v["two_piece"])
            four_sums[v["four_piece"]] = four_sums.get(v["four_piece"], 0.0) + v["q"]
        assert sum(four_sums.values()) == pytest.approx(1.0, abs=0.01), unit["key"]


def test_every_agent_has_slot_mains_and_patch(zzz_datasets):
    meta, _, _ = zzz_datasets
    for unit in meta["agents"]:
        assert unit["slot_mains"]["4"], unit["key"]
        assert unit["slot_mains"]["5"], unit["key"]
        assert unit["slot_mains"]["6"], unit["key"]
        assert unit["build_patch"], unit["key"]
        assert unit["tier"] in ("T0", "T0.5", "T1"), unit["key"]


def test_archetypes_reference_known_units(zzz_datasets):
    meta, _, _ = zzz_datasets
    keys = {u["key"] for u in meta["agents"]}
    assert 10 <= len(meta["archetypes"]) <= 15
    for team in meta["archetypes"]:
        assert team["w"] == 1.0
        assert set(team["members"]) <= keys, team["key"]


def test_stage_set_consistency(zzz_datasets):
    meta, stages, sets = zzz_datasets
    stage_keys = set()
    for stage in stages["stages"]:
        assert len(stage["sets"]) == 2
        assert stage["battery_cost"] == 60
        for set_key in stage["sets"]:
            assert set_key in sets, stage["key"]
            assert sets[set_key]["farmable"] is True
            assert sets[set_key]["farm_stage"] == stage["key"]
        stage_keys.add(stage["key"])
    farmable = {k for k, s in sets.items() if s["farmable"]}
    assert {k for k, s in sets.items() if s.get("farm_stage")} == farmable
    assert len(farmable) == 2 * len(stages["stages"])
    # sets the meta asks for must exist even when not farmable (e.g. event sets)
    for unit in meta["agents"]:
        for v in unit["build_variants"]:
            for key in (v["four_piece"], v["two_piece"]):
                if key:
                    assert key in sets


def test_nonfarmable_sets_have_no_stage(zzz_datasets):
    _, _, sets = zzz_datasets
    for key, s in sets.items():
        if not s["farmable"]:
            assert s["farm_stage"] is None, key


def test_verified_slot_pools():
    pools = {s.key: set(s.main_stat_pool) for s in gear_rules.GEAR_SLOTS}
    assert pools["1"] == {"hp"} and pools["2"] == {"atk"} and pools["3"] == {"def"}
    assert {"crit_rate", "crit_dmg"} <= pools["4"]
    assert "anomaly_proficiency" in pools["4"]
    assert "pen_ratio" in pools["5"]
    assert {"physical_dmg", "fire_dmg", "ice_dmg", "electric_dmg", "ether_dmg"} <= pools["5"]
    assert {"anomaly_mastery", "energy_regen", "impact"} <= pools["6"]
    assert "impact" not in pools["4"] and "crit_rate" not in pools["5"]


def test_scarcity_flags_elemental_sets_harder():
    units = [
        _unit("a", [{"four_piece": "elem_set", "two_piece": "mixed_set", "q": 1.0}],
              slot_mains={"4": [["crit_rate"]], "5": [["fire_dmg"]], "6": [["atk_pct"]]}),
        _unit("b", [{"four_piece": "crit_set", "two_piece": "crit_set", "q": 1.0}],
              slot_mains={"4": [["crit_rate"]], "5": [["atk_pct"]], "6": [["energy_regen"]]}),
        _unit("c", [{"four_piece": "boring_set", "two_piece": "crit_set", "q": 1.0}],
              slot_mains={"4": [["atk_pct"]], "5": [["atk_pct"]], "6": [["atk_pct"]]}),
    ]
    detail = zzz_farm.scarcity_by_set(units)
    assert detail["elem_set"]["severity"] == "severe_v"
    assert detail["elem_set"]["boost"] == 1.5
    assert detail["mixed_set"]["severity"] == "severe_v"
    assert detail["crit_set"]["severity"] == "severe_iv_vi"
    assert detail["boring_set"]["severity"] == "meaningful"


def test_build_farm_plan_empty_inventory_ranks_stages():
    from game_companion.core.games.registry import get_adapter

    adapter = get_adapter("zzz")
    plan = adapter.build_farm_plan([], beta=1.2)
    assert plan is not None
    assert plan["set_rows"]
    assert plan["stage_rows"]
    # no inventory: demanded sets with a target show zero coverage; sets that
    # are only alternatives (target 0) show no coverage value at all
    assert all(r["coverage"] in (0.0, None) for r in plan["set_rows"])
    assert any(r["coverage"] == 0.0 for r in plan["set_rows"])
    assert plan["inventory_summary"]["discs"] == 0
    assert plan["beta_choices"] == [1.0, 1.2, 1.3, 1.5]


def test_base_adapter_has_no_plan():
    from game_companion.core.games.registry import get_adapter

    assert get_adapter("hsr").build_farm_plan([]) is None
