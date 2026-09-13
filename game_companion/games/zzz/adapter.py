"""The ZZZ GameAdapter: all Zenless Zone Zero specifics live here."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from importlib import resources
from pathlib import Path
from typing import Any

from game_companion.config import get_settings
from game_companion.core.games.base import (
    LABEL_HEURISTIC,
    EncounterModeDefinition,
    GameAdapter,
    GearEvaluation,
    GearSlotDefinition,
    ScoreComponent,
    ScreenshotSpec,
    SkillDefinition,
    SourceDefinition,
    StatDefinition,
    TeamRules,
    Terminology,
)
from game_companion.errors import ValidationError
from game_companion.games.zzz import gear_rules, resource_rules, team_rules
from game_companion.games.zzz import sources as zzz_sources
from game_companion.games.zzz.stats import SKILL_DEFINITIONS, STAT_DEFINITIONS
from game_companion.games.zzz.terminology import ATTRIBUTE_NAMES, SPECIALTY_NAMES


def _prompt(name: str) -> str:
    return (
        resources.files("game_companion.games.zzz")
        .joinpath("prompts", f"{name}.md")
        .read_text(encoding="utf-8")
    )


class ZZZAdapter(GameAdapter):
    game_id = "zzz"
    display_name = "Zenless Zone Zero"
    version = "1.0.0"

    def __init__(self, data_dir: Path | None = None) -> None:
        base = data_dir or get_settings().resolved_data_dir
        self._overrides_dir = base / "overrides" / "zzz"
        self._requirements = resource_rules.load_data_json(
            "resource_requirements", self._overrides_dir
        )
        self._agents: dict[str, dict] = resource_rules.load_data_json(
            "agents", self._overrides_dir
        ).get("agents", {})
        self._progression = resource_rules.load_data_json("progression", self._overrides_dir)
        self._sets = resource_rules.load_data_json("drive_disc_sets", self._overrides_dir).get(
            "sets", []
        )
        self._name_index: dict[str, str] = {}
        for key, meta in self._agents.items():
            self._name_index[key] = key
            self._name_index[key.replace("_", " ")] = key
            self._name_index[str(meta.get("name", "")).lower()] = key

    # -- identity / terminology ------------------------------------------------

    def terminology(self) -> Terminology:
        return Terminology(
            character="Agent",
            character_plural="Agents",
            equipment="W-Engine",
            equipment_plural="W-Engines",
            gear="Drive Disc",
            gear_plural="Drive Discs",
            duplication="Mindscape",
            special_progression="Core Skill",
        )

    # -- rules -------------------------------------------------------------------

    def team_rules(self) -> TeamRules:
        return team_rules.TEAM_RULES

    def gear_slots(self) -> list[GearSlotDefinition]:
        return gear_rules.GEAR_SLOTS

    def stat_definitions(self) -> list[StatDefinition]:
        return list(STAT_DEFINITIONS)

    def skill_definitions(self) -> list[SkillDefinition]:
        return list(SKILL_DEFINITIONS)

    def resource_definitions(self) -> list[resource_rules.ResourceDefinition]:
        return resource_rules.resource_definitions(self._requirements)

    def threshold_config(self) -> resource_rules.ResourceThresholdConfig:
        return resource_rules.THRESHOLD_CONFIG

    def gear_sets(self) -> list[dict[str, Any]]:
        return [dict(s) for s in self._sets]

    def equipment_rules(self) -> dict[str, Any]:
        return {
            "noun": "W-Engine",
            "refinement_name": "Stars",
            "level_cap": self._progression.get("_wengine_level_cap", {}).get("value", 60),
            "level_cap_verified": self._progression.get("_wengine_level_cap", {}).get(
                "verified", False
            ),
        }

    def progression_rules(self) -> dict[str, Any]:
        return {
            "level_cap": self._progression.get("level_cap", {}),
            "ascension_stages": self._progression.get("ascension_stages", {}),
            "skill_targets": self._progression.get("skill_targets", {}),
            "gear_level_cap": self._progression.get("_drive_disc_level_cap", {}),
        }

    def encounter_modes(self) -> list[EncounterModeDefinition]:
        return [
            EncounterModeDefinition(
                key="shiyu_defense",
                name="Shiyu Defense",
                slot_count=2,
                description="starter data — slot count/constraints may rotate by season",
            ),
            EncounterModeDefinition(
                key="deadly_assault",
                name="Deadly Assault",
                slot_count=3,
                description="starter data — three separate enemy squads, one team per slot",
            ),
        ]

    def source_registry(self) -> list[SourceDefinition]:
        return list(zzz_sources.SOURCES)

    def code_config(self) -> dict[str, Any]:
        return {
            "discovery_source_keys": zzz_sources.CODE_DISCOVERY_SOURCE_KEYS,
            "notes": zzz_sources.CODE_CONFIG_NOTES,
        }

    def persona_flavors(self) -> list[dict[str, Any]]:
        return [
            {"id": "hustle_manager", "description": "energetic profit-minded manager vibe"},
            {"id": "calm_tactician", "description": "composed step-by-step instructor vibe"},
        ]

    def tutor_notes(self) -> dict[str, Any]:
        return {
            "controls": (
                "When giving button-by-button ZZZ rotations, use ability names "
                "(Basic Attack, Dodge, Assist/Defensive Assist, Special Attack, "
                "EX Special Attack, Chain Attack, Ultimate, Quick Assist, Switch) "
                "rather than raw platform buttons, and note that inputs vary by platform."
            ),
            "team_size": 3,
        }

    # -- screenshot ingestion ------------------------------------------------------

    def screenshot_specs(self) -> dict[str, ScreenshotSpec]:
        from game_companion.games.zzz import screenshot_schemas as schemas

        return {
            "character_overview": ScreenshotSpec(
                key="character_overview",
                description="Agent overview/attribute screen",
                prompt=_prompt("agent_overview"),
                schema=schemas.AgentOverviewCandidate,
            ),
            "skills": ScreenshotSpec(
                key="skills",
                description="Agent skill levels screen",
                prompt=_prompt("skills"),
                schema=schemas.SkillsCandidate,
            ),
            "equipment": ScreenshotSpec(
                key="equipment",
                description="Equipped W-Engine screen",
                prompt=_prompt("wengine"),
                schema=schemas.WEngineCandidate,
            ),
            "gear_list": ScreenshotSpec(
                key="gear_list",
                description="Drive Disc loadout list screen",
                prompt=_prompt("drive_discs"),
                schema=schemas.DriveDiscListCandidate,
            ),
            "gear_detail": ScreenshotSpec(
                key="gear_detail",
                description="Single Drive Disc detail screen",
                prompt=_prompt("drive_disc_detail"),
                schema=schemas.DriveDiscDetailCandidate,
            ),
            "resources": ScreenshotSpec(
                key="resources",
                description="Inventory/resources screen",
                prompt=_prompt("resources"),
                schema=schemas.ResourcesCandidate,
            ),
        }

    # -- validation / lookup -----------------------------------------------------

    _ALLOWED_DATA_KEYS = {"attribute", "specialty", "faction", "nickname"}

    def validate_character_data(self, data: Mapping[str, Any]) -> dict[str, Any]:
        cleaned: dict[str, Any] = {}
        for key, value in dict(data).items():
            if key not in self._ALLOWED_DATA_KEYS:
                raise ValidationError(
                    f"unknown ZZZ character data key '{key}' "
                    f"(allowed: {sorted(self._ALLOWED_DATA_KEYS)})"
                )
            if key == "attribute" and value is not None and value not in ATTRIBUTE_NAMES:
                raise ValidationError(
                    f"unknown attribute '{value}' (allowed: {sorted(ATTRIBUTE_NAMES)})"
                )
            if key == "specialty" and value is not None and value not in SPECIALTY_NAMES:
                raise ValidationError(
                    f"unknown specialty '{value}' (allowed: {sorted(SPECIALTY_NAMES)})"
                )
            cleaned[key] = value
        return cleaned

    def character_meta(self, key: str) -> dict[str, Any] | None:
        resolved = self._name_index.get(key.lower()) or self._name_index.get(key)
        if resolved is None:
            return None
        meta = self._agents.get(resolved, {})
        return {
            "key": resolved,
            "name": meta.get("name"),
            "rarity": meta.get("rarity"),
            "attribute": meta.get("attribute"),
            "specialty": meta.get("specialty"),
            "faction": meta.get("faction"),
            "starter_data": True,
        }

    def resolve_character_key(self, name: str) -> str | None:
        return self._name_index.get(name.strip().lower())

    # -- scoring hooks (heuristic, explainable) -------------------------------------

    def score_gear(self, gear: Mapping[str, Any], context: Mapping[str, Any]) -> GearEvaluation:
        return gear_rules.score_gear(gear, context, self.character_meta)

    def score_team(
        self, member_keys: Sequence[str], context: Mapping[str, Any]
    ) -> list[ScoreComponent]:
        return team_rules.score_team(member_keys, self.character_meta, context)

    def character_slot_fit(
        self, character_key: str, encounter_constraints: Mapping[str, Any]
    ) -> float:
        return team_rules.character_slot_fit(
            character_key, encounter_constraints, self.character_meta
        )


    def score_equipment_for_character(
        self, character_key: str, equipment: Mapping[str, Any]
    ) -> ScoreComponent:
        rarity_score = {"S": 8.0, "A": 5.0, "B": 2.0}.get(str(equipment.get("rarity") or ""), 3.0)
        level_cap = float(self.equipment_rules().get("level_cap") or 60)
        level = equipment.get("level")
        level_score = 1.5 * (float(level) / level_cap) if level else 0.0
        refinement = equipment.get("refinement")
        refinement_score = 0.25 * refinement if refinement else 0.0
        value = min(10.0, rarity_score + level_score + refinement_score)
        detail = (
            f"rarity {equipment.get('rarity') or '?'} base {rarity_score:g}, "
            f"level {level if level is not None else '?'} contributes {level_score:.1f}, "
            f"stars {refinement if refinement is not None else '?'} contributes {refinement_score:.2f}"
        )
        return ScoreComponent("equipment_quality", value, 10, LABEL_HEURISTIC, detail)
