"""Neverness to Everness adapter — scaffolded from launch-window research.

Everything uncertain is marked [verify] (see data/terminology.json notes and
docs/game-adapters-research.md §5). Character metadata, endgame modes and
official attribute/role lists arrive via `bootstrap-game nte` once Prydwen's
NTE data settles — nothing is invented here.
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


def _prompt(name: str) -> str:
    return (
        resources.files("game_companion.games.nte")
        .joinpath("prompts", f"{name}.md")
        .read_text(encoding="utf-8")
    )


class NTECharacterOverview(BaseModel):
    character_name: str | None = None
    level: int | None = None
    awakening_level: int | None = None
    extraction_confidence: float | None = None


class NTEAdapter(GameAdapter):
    game_id = "nte"
    display_name = "Neverness to Everness"
    version = "0.1.0"

    def terminology(self) -> Terminology:
        return Terminology(
            character="Character",
            character_plural="Characters",
            equipment="Arc",
            equipment_plural="Arcs",
            gear="Cartridge",
            gear_plural="Cartridges",
            duplication="Awakening",
            special_progression="Skill track",
        )

    def team_rules(self) -> TeamRules:
        return TeamRules(min_size=1, max_size=4)

    def gear_slots(self) -> list[GearSlotDefinition]:
        return [
            GearSlotDefinition(key=s.key, name=s.name, main_stat_pool=s.main_stat_pool)
            for s in self.gear_families()[0].slots
        ]

    def gear_families(self) -> list[GearFamily]:
        import json

        raw = json.loads(
            resources.files("game_companion.games.nte")
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
                    rarity_scale=family.get("rarity_scale", "SAB"),
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
            StatDefinition(key="hp_percent", name="HP%", kind="percent"),
            StatDefinition(key="atk_percent", name="ATK%", kind="percent"),
            StatDefinition(key="def_percent", name="DEF%", kind="percent"),
            StatDefinition(key="crit_rate", name="CRIT Rate", kind="percent"),
            StatDefinition(key="crit_dmg", name="CRIT DMG", kind="percent"),
            StatDefinition(key="universal_dmg", name="Universal DMG%", kind="percent"),
        ]

    def skill_definitions(self) -> list[SkillDefinition]:
        return [
            SkillDefinition(key="basic", name="Basic", max_level=1,
                            max_level_note="starter data — verify scale"),
            SkillDefinition(key="skill", name="Skill", max_level=1,
                            max_level_note="starter data — verify scale"),
            SkillDefinition(key="ultimate", name="Ultimate", max_level=1,
                            max_level_note="starter data — verify scale"),
        ]

    def resource_definitions(self) -> list[ResourceDefinition]:
        return [
            ResourceDefinition(key="annulith", name="Annulith", category="pull_currency",
                               notes="premium pull currency; Riftcrystal converts 1:1"),
            ResourceDefinition(key="riftcrystal", name="Riftcrystal", category="pull_currency",
                               notes="paid tier; converts to Annulith"),
            ResourceDefinition(key="tri_key", name="Tri-Key", category="pull_ticket_limited",
                               notes="starter data — verify banner mapping"),
            ResourceDefinition(key="solid_dice", name="Solid Dice", category="pull_ticket_standard",
                               notes="starter data — verify banner mapping"),
            ResourceDefinition(key="fabricated_dice", name="Fabricated Dice",
                               category="pull_ticket_standard",
                               notes="starter data — verify banner mapping"),
        ]

    def encounter_modes(self) -> list[EncounterModeDefinition]:
        return [
            EncounterModeDefinition(
                key="nte_endgame", name="Endgame (verify)",
                slot_count=1,
                description="starter data — official endgame mode names/rules not yet encoded",
            )
        ]

    def source_registry(self) -> list[SourceDefinition]:
        return [
            SourceDefinition(key="prydwen_nte", name="Prydwen NTE",
                             url="https://www.prydwen.gg/neverness-to-everness",
                             category="database", trust=4,
                             notes="richest single source; Characters, Arcs, Cartridges, banners"),
            SourceDefinition(key="game8_nte", name="Game8 NTE", url="https://game8.co/games/Neverness-to-Everness",
                             category="wiki", trust=3),
        ]

    def screenshot_specs(self) -> dict[str, ScreenshotSpec]:
        return {
            "character_overview": ScreenshotSpec(
                key="character_overview",
                description="Character overview screen (generic placeholder)",
                prompt=_prompt("character_overview"),
                schema=NTECharacterOverview,
            ),
        }

    def score_gear(self, gear: Mapping[str, Any], context: Mapping[str, Any]) -> GearEvaluation:
        return GearEvaluation(
            verdict="speculative",
            score=50.0,
            reasons=["NTE starter data has no per-role gear weights yet; nothing invented"],
            components=[ScoreComponent("placeholder", 5.0, 10, LABEL_HEURISTIC, "no starter data")],
        )

    def catalog_sources(self) -> dict[str, dict[str, Any]]:
        from game_companion.games.nte import catalog as nte_catalog

        return nte_catalog.CATALOG_SOURCES

    def catalog_transform(self, source_key: str, payload: Any) -> list[dict[str, Any]]:
        from game_companion.games.nte import catalog as nte_catalog

        return nte_catalog.catalog_transform(source_key, payload)

    def theme(self) -> dict[str, str]:
        return {
            "accent": "#4fd8c4",
            "accent2": "#9d7bff",
            "bg": "#101816",
            "bg2": "#152420",
            "card": "#14201d",
            "radius": "14px",
            "mood": "Signals from the Fair",
            "font": "Chakra Petch",
            "logo": "/ui/static/images/logos/nte.webp",
            "logo_filter": "invert(1) brightness(1.1)",  # emblem is dark grey; lift it onto the dark bg
            "currency": "Annulith",
            "currency_colors": "#4fd8c4,#9d7bff,#e8fff9,#2b9d8c",
            "currency_shape": "image",
            "currency_icon": "/ui/static/images/currency/annulith.webp",
        }

    def codes_source(self) -> dict[str, Any] | None:
        from game_companion.games.nte import catalog as nte_catalog

        return dict(nte_catalog.CODES_SOURCE)

    def codes_transform(self, payload: Any) -> list[dict[str, Any]]:
        from game_companion.games.nte import catalog as nte_catalog

        return nte_catalog.codes_transform(payload)

    def media_url(self, kind: str, key: str, meta: Any = None) -> str | None:
        base = "https://cdn.prydwen.gg/images/nte"
        slug = key.strip().lower().replace("_", "-")
        if kind == "character":
            return f"{base}/characters/{slug}_card.webp"
        return None

    def score_team(self, member_keys: Sequence[str], context: Mapping[str, Any]) -> list[ScoreComponent]:
        return [
            ScoreComponent(
                "team_synergy",
                5.0,
                10,
                LABEL_HEURISTIC,
                "character metadata not bootstrapped yet — neutral fit",
            )
        ]
