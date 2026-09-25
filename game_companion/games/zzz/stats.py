"""ZZZ stat and skill definitions."""

from __future__ import annotations

from game_companion.core.games.base import SkillDefinition, StatDefinition
from game_companion.games.zzz.terminology import SKILL_NAMES

STAT_DEFINITIONS = [
    StatDefinition(key="hp", name="HP", kind="flat"),
    StatDefinition(key="hp_pct", name="HP%", kind="percent"),
    StatDefinition(key="atk", name="ATK", kind="flat"),
    StatDefinition(key="atk_pct", name="ATK%", kind="percent"),
    StatDefinition(key="def", name="DEF", kind="flat"),
    StatDefinition(key="def_pct", name="DEF%", kind="percent"),
    StatDefinition(key="impact", name="Impact", kind="flat"),
    StatDefinition(key="crit_rate", name="CRIT Rate", kind="percent"),
    StatDefinition(key="crit_dmg", name="CRIT DMG", kind="percent"),
    StatDefinition(key="anomaly_proficiency", name="Anomaly Proficiency", kind="flat"),
    StatDefinition(key="anomaly_mastery", name="Anomaly Mastery", kind="percent"),
    StatDefinition(key="pen_ratio", name="Pen Ratio", kind="percent"),
    StatDefinition(key="energy_regen", name="Energy Regen", kind="percent"),
    # Elemental damage mains (slot V only). wind_dmg seen in Prydwen build
    # data (3.2) — UNKNOWN-NEEDS DATA until corroborated in-game.
    StatDefinition(key="physical_dmg", name="Physical DMG", kind="percent"),
    StatDefinition(key="fire_dmg", name="Fire DMG", kind="percent"),
    StatDefinition(key="ice_dmg", name="Ice DMG", kind="percent"),
    StatDefinition(key="electric_dmg", name="Electric DMG", kind="percent"),
    StatDefinition(key="ether_dmg", name="Ether DMG", kind="percent"),
    StatDefinition(key="wind_dmg", name="Wind DMG", kind="percent"),
]

# Starter max levels: combat skills cap at 12 in-game; Core Skill is capped
# here at 7 pending verification (see max_level_note).
SKILL_DEFINITIONS = [
    SkillDefinition(key="basic_attack", name=SKILL_NAMES["basic_attack"], max_level=12),
    SkillDefinition(key="dodge", name=SKILL_NAMES["dodge"], max_level=12),
    SkillDefinition(key="assist", name=SKILL_NAMES["assist"], max_level=12),
    SkillDefinition(key="special_attack", name=SKILL_NAMES["special_attack"], max_level=12),
    SkillDefinition(key="chain_attack", name=SKILL_NAMES["chain_attack"], max_level=12),
    SkillDefinition(
        key="core_skill",
        name=SKILL_NAMES["core_skill"],
        max_level=7,
        max_level_note="starter data — verify the in-game Core Skill cap",
    ),
]
