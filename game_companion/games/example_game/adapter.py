"""Example/fake game adapter — structurally DIFFERENT from ZZZ on purpose.

Aether Tactics has: 4-member teams, two gear slots ("talisman"/"relic"),
different stats (power/speed/focus), different skills, and known resource
requirements. The adapter-contract tests run identical core scenarios against
this game and ZZZ to prove nothing ZZZ-shaped leaked into the core.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import BaseModel

from game_companion.core.games.base import (
    LABEL_HEURISTIC,
    EncounterModeDefinition,
    GameAdapter,
    GearEvaluation,
    GearSlotDefinition,
    ResourceDefinition,
    ResourceThresholdConfig,
    ScoreComponent,
    ScreenshotSpec,
    SkillDefinition,
    SourceDefinition,
    StatDefinition,
    TeamRules,
    Terminology,
)
from game_companion.errors import ValidationError

_ROSTER = {
    "aria": {"name": "Aria", "tag": "wind", "role": "striker"},
    "brann": {"name": "Brann", "tag": "stone", "role": "warden"},
    "cinder": {"name": "Cinder", "tag": "ember", "role": "striker"},
    "dusk": {"name": "Dusk", "tag": "wind", "role": "weaver"},
    "echo": {"name": "Echo", "tag": "tide", "role": "weaver"},
    "flint": {"name": "Flint", "tag": "ember", "role": "striker"},
}


class ExampleOverviewCandidate(BaseModel):
    character_name: str | None = None
    level: int | None = None
    tag: str | None = None


class ExampleGameAdapter(GameAdapter):
    game_id = "example"
    display_name = "Aether Tactics (Example)"
    version = "1.0.0"

    def terminology(self) -> Terminology:
        return Terminology(
            character="Vanguard",
            character_plural="Vanguards",
            equipment="Sigil",
            equipment_plural="Sigils",
            gear="Charm",
            gear_plural="Charms",
            duplication="Echo",
            special_progression="Attunement",
        )

    def team_rules(self) -> TeamRules:
        return TeamRules(min_size=4, max_size=4)

    def gear_slots(self) -> list[GearSlotDefinition]:
        return [
            GearSlotDefinition(key="talisman", name="Talisman", main_stat_pool=("power", "focus")),
            GearSlotDefinition(key="relic", name="Relic", main_stat_pool=("speed", "power")),
        ]

    def stat_definitions(self) -> list[StatDefinition]:
        return [
            StatDefinition(key="power", name="Power", kind="flat"),
            StatDefinition(key="speed", name="Speed", kind="flat"),
            StatDefinition(key="focus", name="Focus", kind="percent"),
        ]

    def skill_definitions(self) -> list[SkillDefinition]:
        return [
            SkillDefinition(key="strike", name="Strike", max_level=10),
            SkillDefinition(key="guard", name="Guard", max_level=10),
        ]

    def resource_definitions(self) -> list[ResourceDefinition]:
        return [
            ResourceDefinition(key="crystal", name="Crystals", single_character_max=500),
            ResourceDefinition(key="gold", name="Gold", single_character_max=100_000),
        ]

    def threshold_config(self) -> ResourceThresholdConfig:
        return ResourceThresholdConfig(low_fraction=0.5)

    def encounter_modes(self) -> list[EncounterModeDefinition]:
        return [
            EncounterModeDefinition(
                key="gauntlet", name="The Gauntlet", slot_count=3, team_size=4
            )
        ]

    def source_registry(self) -> list[SourceDefinition]:
        return [
            SourceDefinition(
                key="example_wiki",
                name="Aether Tactics Wiki (fake)",
                url="https://example.invalid/aether-tactics",
                category="wiki",
                trust=3,
            )
        ]

    def screenshot_specs(self) -> dict[str, ScreenshotSpec]:
        return {
            "character_overview": ScreenshotSpec(
                key="character_overview",
                description="Vanguard overview screen",
                prompt="Extract the character's name, level and tag. Use null if unreadable.",
                schema=ExampleOverviewCandidate,
            )
        }

    def validate_character_data(self, data: Mapping[str, Any]) -> dict[str, Any]:
        cleaned = dict(data)
        tag = cleaned.get("tag")
        if tag is not None and tag not in {r["tag"] for r in _ROSTER.values()}:
            raise ValidationError(f"unknown tag '{tag}' for Aether Tactics")
        return cleaned

    def character_meta(self, key: str) -> dict[str, Any] | None:
        meta = _ROSTER.get(key)
        return dict(meta) if meta else None

    def resolve_character_key(self, name: str) -> str | None:
        lowered = name.strip().lower()
        return lowered if lowered in _ROSTER else None

    def score_gear(self, gear: Mapping[str, Any], context: Mapping[str, Any]) -> GearEvaluation:
        main = gear.get("main_stat_key")
        role = context.get("role") or "striker"
        desired = "power" if role == "striker" else "speed"
        fit = 1.0 if main == desired else (0.4 if main else 0.0)
        subs = sum(
            0.2
            for sub in (gear.get("substats") or [])
            if sub.get("key") in ("power", "speed", "focus")
        )
        score = round(100 * (0.5 * fit + 0.5 * min(subs, 1.0)), 1)
        verdict = "strong" if score >= 70 else "useful" if score >= 45 else "weak"
        return GearEvaluation(
            verdict=verdict,
            score=score,
            reasons=[
                f"main stat {main} vs desired {desired} for role {role}",
                f"{len(list(subs for sub in (gear.get('substats') or [])))} relevant substats",
            ],
        )

    def score_team(
        self, member_keys: Sequence[str], context: Mapping[str, Any]
    ) -> list[ScoreComponent]:
        tags = [(_ROSTER.get(k) or {}).get("tag") for k in member_keys]
        distinct = len({t for t in tags if t})
        same_pairs = len(tags) - len({t for t in tags if t})
        synergy = min(10.0, distinct * 2.5 + same_pairs * 2.0)
        return [
            ScoreComponent(
                "tag_synergy",
                synergy,
                10,
                LABEL_HEURISTIC,
                f"{distinct} distinct tags, {same_pairs} same-tag pairs",
            )
        ]

    def character_slot_fit(
        self, character_key: str, encounter_constraints: Mapping[str, Any]
    ) -> float:
        meta = _ROSTER.get(character_key) or {}
        preferred = encounter_constraints.get("preferred_tags") or []
        base = 5.0
        if meta.get("tag") in preferred:
            base += 4.0
        if meta.get("role") in (encounter_constraints.get("preferred_roles") or []):
            base += 1.0
        return min(10.0, base)

    def score_equipment_for_character(
        self, character_key: str, equipment: Mapping[str, Any]
    ) -> ScoreComponent:
        level = equipment.get("level") or 0
        return ScoreComponent(
            "sigil_quality",
            min(10.0, level / 2.0),
            10,
            LABEL_HEURISTIC,
            f"level {level} out of cap 20",
        )
