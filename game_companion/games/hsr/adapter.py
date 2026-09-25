"""Honkai: Star Rail adapter — first adapter built through the M24 workbench.

Starter data is honest: structure and naming come from public wikis and
`docs/game-adapters-research.md`; anything uncertain carries a
``starter_data`` marker and never pretends to be verified. Character roster
metadata arrives via `bootstrap-game` (StarRailRes), not hand-invention.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from importlib import resources
from typing import Any

from pydantic import BaseModel

from game_companion.core.games.base import (
    LABEL_HEURISTIC,
    EncounterModeDefinition,
    GameAdapter,
    GearEvaluation,
    GearFamily,
    GearSlotDefinition,
    ResourceDefinition,
    ScoreComponent,
    ScreenshotSpec,
    SkillDefinition,
    SourceDefinition,
    StatDefinition,
    TeamRules,
    Terminology,
)
from game_companion.games.hsr import bootstrap as hsr_bootstrap


def _prompt(name: str) -> str:
    return (
        resources.files("game_companion.games.hsr")
        .joinpath("prompts", f"{name}.md")
        .read_text(encoding="utf-8")
    )


class HSRCharacterOverview(BaseModel):
    character_name: str | None = None
    level: int | None = None
    duplication_level: int | None = None  # Eidolon E0-E6
    extraction_confidence: float | None = None


class HSRAdapter(GameAdapter):
    game_id = "hsr"
    display_name = "Honkai: Star Rail"
    version = "0.1.0"

    def terminology(self) -> Terminology:
        return Terminology(
            character="Character",
            character_plural="Characters",
            equipment="Light Cone",
            equipment_plural="Light Cones",
            gear="Relic",
            gear_plural="Relics",
            duplication="Eidolon",
            special_progression="Traces",
        )

    def team_rules(self) -> TeamRules:
        return TeamRules(min_size=1, max_size=4)

    def gear_slots(self) -> list[GearSlotDefinition]:
        slots: list[GearSlotDefinition] = []
        for family in self.gear_families():
            slots.extend(GearSlotDefinition(key=s.key, name=f"{s.name}", main_stat_pool=s.main_stat_pool) for s in family.slots)
        return slots

    def gear_families(self) -> list[GearFamily]:
        import json

        raw = json.loads(
            resources.files("game_companion.games.hsr")
            .joinpath("data", "gear_families.json")
            .read_text(encoding="utf-8")
        )
        families = []
        for family in raw.get("families", []):
            families.append(
                GearFamily(
                    key=family["key"],
                    display=family.get("display", family["key"]),
                    slot_count=family.get("slot_count", 0),
                    set_rule=family.get("set_rule", "fixed_pieces"),
                    set_sizes=tuple(family.get("set_sizes", ())),
                    rarity_scale=family.get("rarity_scale", "stars5"),
                    max_level=family.get("max_level"),
                    max_substats=family.get("max_substats"),
                    starter_data=family.get("starter_data", False),
                    slots=tuple(
                        GearSlotDefinition(
                            key=slot["key"],
                            name=slot.get("display", slot["key"]),
                            main_stat_pool=tuple(slot.get("main_stat_pool", ())),
                        )
                        for slot in family.get("slots", ())
                    ),
                )
            )
        return families

    def stat_definitions(self) -> list[StatDefinition]:
        return [
            StatDefinition(key="flat_hp", name="HP", kind="flat"),
            StatDefinition(key="flat_atk", name="ATK", kind="flat"),
            StatDefinition(key="flat_def", name="DEF", kind="flat"),
            StatDefinition(key="hp_percent", name="HP%", kind="percent"),
            StatDefinition(key="atk_percent", name="ATK%", kind="percent"),
            StatDefinition(key="def_percent", name="DEF%", kind="percent"),
            StatDefinition(key="crit_rate", name="CRIT Rate", kind="percent"),
            StatDefinition(key="crit_dmg", name="CRIT DMG", kind="percent"),
            StatDefinition(key="speed_flat", name="SPD", kind="flat"),
            StatDefinition(key="break_effect", name="Break Effect", kind="percent"),
            StatDefinition(key="effect_hit_rate", name="Effect Hit Rate", kind="percent"),
            StatDefinition(key="effect_res", name="Effect RES", kind="percent"),
            StatDefinition(key="outgoing_healing", name="Outgoing Healing", kind="percent"),
            StatDefinition(key="energy_regen", name="Energy Regeneration Rate", kind="percent"),
            StatDefinition(key="attribute_dmg", name="DMG Boost", kind="percent"),
        ]

    def skill_definitions(self) -> list[SkillDefinition]:
        return [
            SkillDefinition(key="basic_attack", name="Basic ATK", max_level=6, max_level_note="starter data — verify per character"),
            SkillDefinition(key="skill", name="Skill", max_level=10, max_level_note="starter data — verify per character"),
            SkillDefinition(key="ultimate", name="Ultimate", max_level=10, max_level_note="starter data — verify per character"),
            SkillDefinition(key="talent", name="Talent", max_level=10, max_level_note="starter data — verify per character"),
            SkillDefinition(key="technique", name="Technique", max_level=1),
        ]

    def resource_definitions(self) -> list[ResourceDefinition]:
        return [
            ResourceDefinition(key="stellar_jade", name="Stellar Jade", category="pull_currency",
                               notes="starter data — premium pull currency"),
            ResourceDefinition(key="oneiric_shard", name="Oneiric Shard", category="pull_currency",
                               notes="paid premium currency; converts to Stellar Jade"),
            ResourceDefinition(key="star_rail_special_pass", name="Star Rail Special Pass",
                               category="pull_ticket_limited", notes="starter data — limited Warp ticket"),
            ResourceDefinition(key="star_rail_pass", name="Star Rail Pass",
                               category="pull_ticket_standard", notes="starter data — standard Warp ticket"),
            ResourceDefinition(key="credits", name="Credits", category="money"),
            ResourceDefinition(key="trailblaze_power", name="Trailblaze Power", category="stamina",
                               notes="starter data — regenerates over time; cap not stored"),
            ResourceDefinition(key="fuel", name="Fuel", category="stamina",
                               notes="consumable that refills Trailblaze Power"),
        ]

    def encounter_modes(self) -> list[EncounterModeDefinition]:
        return [
            EncounterModeDefinition(
                key="memory_of_chaos", name="Memory of Chaos", slot_count=2,
                description="starter data — two sides, one team each; rotates every patch",
            ),
            EncounterModeDefinition(
                key="pure_fiction", name="Pure Fiction", slot_count=2,
                description="starter data — two sides; save-file scoring",
            ),
            EncounterModeDefinition(
                key="apocalyptic_shadow", name="Apocalyptic Shadow", slot_count=2,
                description="starter data — two sides; boss-focused",
            ),
        ]

    def source_registry(self) -> list[SourceDefinition]:
        return [
            SourceDefinition(key="starrailres", name="StarRailRes",
                             url="https://github.com/Mar-7th/StarRailRes",
                             category="database", trust=5,
                             notes="structured multilang JSON; bootstrap source"),
            SourceDefinition(key="hakush", name="hakush.in", url="https://hakush.in/hsr",
                             category="database", trust=4,
                             notes="raw JSON endpoints; multi-game"),
            SourceDefinition(key="prydwen", name="Prydwen HSR", url="https://www.prydwen.gg/star-rail/",
                             category="build_guide", trust=4,
                             notes="tier lists, teams, build guides"),
        ]

    def code_config(self) -> dict[str, Any]:
        return {
            "discovery_source_keys": ["official"],
            "notes": "HSR codes are rare; redeem at https://hsr.hoyoverse.com/gift",
        }

    def screenshot_specs(self) -> dict[str, ScreenshotSpec]:
        return {
            "character_overview": ScreenshotSpec(
                key="character_overview",
                description="Character detail screen (level, Eidolon)",
                prompt=_prompt("character_overview"),
                schema=HSRCharacterOverview,
            ),
        }

    def bootstrap_sources(self) -> dict[str, dict[str, Any]]:
        return hsr_bootstrap.BOOTSTRAP_SOURCES

    def bootstrap_transform(self, source_key: str, payload: Any) -> list[dict[str, Any]]:
        return hsr_bootstrap.transform(source_key, payload)

    def catalog_sources(self) -> dict[str, dict[str, Any]]:
        from game_companion.games.hsr import catalog as hsr_catalog

        return hsr_catalog.CATALOG_SOURCES

    def catalog_transform(self, source_key: str, payload: Any) -> list[dict[str, Any]]:
        from game_companion.games.hsr import catalog as hsr_catalog

        return hsr_catalog.catalog_transform(source_key, payload)

    def theme(self) -> dict[str, str]:
        # HSR menus: deep-space navy + warm gold trim (#c9a36a) + purple accents
        return {
            "accent": "#c9a36a",
            "accent2": "#8a5fcc",
            "bg": "#0d1020",
            "bg2": "#121a30",
            "card": "#191d2e",
            "line": "#2a3050",
            "radius": "16px",
            "mood": "Aboard the Astral Express",
            "font": "Poppins",
            "logo": "/ui/static/images/logos/hsr.webp",
            "bg_image": "https://cdn.prydwen.gg/images/star-rail/website_bg.webp",
            "currency": "Stellar Jade",
            "currency_colors": "#5fd4a0,#bfe8d2,#2e8f6b,#ffd24a",
            "currency_shape": "image",
            "currency_icon": "/ui/static/images/currency/stellar_jade.webp",
        }

    def media_url(self, kind: str, key: str, meta: Any = None) -> str | None:
        base = "https://raw.githubusercontent.com/Mar-7th/StarRailRes/master/icon"
        clean = key.strip().lower()
        if kind == "character" and clean.isdigit():
            return f"{base}/avatar/{clean}.png"
        if kind == "equipment" and clean.isdigit():
            return f"{base}/light_cone/{clean}.png"
        return None

    def codes_source(self) -> dict[str, dict[str, Any]] | None:
        from game_companion.games.hsr import catalog as hsr_catalog

        return dict(hsr_catalog.CODES_SOURCE)

    def codes_transform(self, payload: Any) -> list[dict[str, Any]]:
        from game_companion.games.hsr import catalog as hsr_catalog

        return hsr_catalog.codes_transform(payload)

    def score_gear(self, gear: Mapping[str, Any], context: Mapping[str, Any]) -> GearEvaluation:
        return GearEvaluation(
            verdict="speculative",
            score=50.0,
            reasons=["HSR starter data has no per-role gear weights yet; nothing invented"],
            components=[ScoreComponent("placeholder", 5.0, 10, LABEL_HEURISTIC, "no starter data")],
        )

    def score_team(self, member_keys: Sequence[str], context: Mapping[str, Any]) -> list[ScoreComponent]:
        return [
            ScoreComponent(
                "team_synergy",
                5.0,
                10,
                LABEL_HEURISTIC,
                "roster metadata not bootstrapped yet — neutral fit; run 'game-companion bootstrap-game hsr'",
            )
        ]
