"""`game-companion new-game <id>` scaffold (M24 adapter workbench).

Generates a complete, working adapter package (contract-suite ready) with
honesty-marked placeholder data, registers it in games/installed.json, and
prints what to fill in next. The LLM then learns the game from
terminology.json — edit that first.
"""

from __future__ import annotations

from pathlib import Path

from game_companion.errors import ValidationError

_REGISTRY_INIT = '''"""{title} game adapter."""

from game_companion.core.games.registry import get_adapter  # noqa: F401
'''

_ADAPTER_TEMPLATE = '''"""{title} adapter — scaffolded by `game-companion new-game`, contract-ready.

Placeholders are honest: stats/resources marked starter_data carry no invented
numbers, and scoring returns labeled "no data" components instead of guessing.
Fill in data/*.json (terminology first!), then flesh out the hooks.
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
        resources.files("game_companion.games.{game_id}")
        .joinpath("prompts", f"{{name}}.md")
        .read_text(encoding="utf-8")
    )


class {class_name}CharacterOverview(BaseModel):
    """Generic extraction schema — replace fields with the real screen's."""

    character_name: str | None = None
    level: int | None = None
    duplication_level: int | None = None
    extraction_confidence: float | None = None


class {class_name}Adapter(GameAdapter):
    game_id = "{game_id}"
    display_name = "{title}"
    version = "0.1.0"

    def terminology(self) -> Terminology:
        table = {{t["key"]: t.get("display", "") for t in self.terminology_table()}}
        return Terminology(
            character=table.get("character", "Character"),
            character_plural=table.get("character_plural", "Characters"),
            equipment=table.get("equipment", "Weapon"),
            equipment_plural=table.get("equipment_plural", "Weapons"),
            gear=table.get("gear", "Gear piece"),
            gear_plural=table.get("gear_plural", "Gear pieces"),
            duplication=table.get("duplication", "Dupes"),
            special_progression=table.get("special_progression", "Skill track"),
        )

    def team_rules(self) -> TeamRules:
        return TeamRules(min_size=1, max_size=4)

    def gear_slots(self) -> list[GearSlotDefinition]:
        return [GearSlotDefinition(key=s.key, name=s.name) for s in self.gear_families()[0].slots]

    def gear_families(self) -> list[GearFamily]:
        from game_companion.core.games.base import GearSlotDefinition as Slot

        return [
            GearFamily(
                key="scaffold_gear",
                display="Gear set",
                slot_count=4,
                set_rule="fixed_pieces",
                set_sizes=(2, 4),
                rarity_scale="stars5",
                max_level=None,
                max_substats=4,
                starter_data=True,
                slots=(
                    Slot(key="slot_1", name="Slot 1"),
                    Slot(key="slot_2", name="Slot 2"),
                    Slot(key="slot_3", name="Slot 3"),
                    Slot(key="slot_4", name="Slot 4"),
                ),
            )
        ]

    def stat_definitions(self) -> list[StatDefinition]:
        return [
            StatDefinition(key="hp_percent", name="HP%", kind="percent"),
            StatDefinition(key="atk_percent", name="ATK%", kind="percent"),
            StatDefinition(key="def_percent", name="DEF%", kind="percent"),
            StatDefinition(key="crit_rate", name="CRIT Rate", kind="percent"),
            StatDefinition(key="crit_dmg", name="CRIT DMG", kind="percent"),
            StatDefinition(key="speed_flat", name="Speed", kind="flat"),
        ]

    def skill_definitions(self) -> list[SkillDefinition]:
        return [
            SkillDefinition(key="basic", name="Basic", max_level=1),
            SkillDefinition(key="skill", name="Skill", max_level=1),
            SkillDefinition(key="ultimate", name="Ultimate", max_level=1),
            SkillDefinition(key="passive", name="Passive", max_level=1),
        ]

    def resource_definitions(self) -> list[ResourceDefinition]:
        return [
            ResourceDefinition(key="pull_currency", name="Pull currency (rename me)", category="pull_currency"),
            ResourceDefinition(key="pull_ticket", name="Pull ticket (rename me)", category="pull_ticket_limited"),
            ResourceDefinition(key="money", name="Money (rename me)", category="money"),
        ]

    def encounter_modes(self) -> list[EncounterModeDefinition]:
        return [
            EncounterModeDefinition(
                key="scaffold_endgame",
                name="Endgame mode (rename me)",
                slot_count=1,
                description="starter data — verify slot count and rules in-game",
            )
        ]

    def source_registry(self) -> list[SourceDefinition]:
        return [
            SourceDefinition(
                key="prydwen",
                name="Prydwen",
                url="https://www.prydwen.gg/",
                category="database",
                trust=4,
                notes="community wiki; data for bootstrap",
            )
        ]

    def screenshot_specs(self) -> dict[str, ScreenshotSpec]:
        return {{
            "character_overview": ScreenshotSpec(
                key="character_overview",
                description="Character overview screen (generic placeholder)",
                prompt=_prompt("character_overview"),
                schema={class_name}CharacterOverview,
            )
        }}

    def score_gear(self, gear: Mapping[str, Any], context: Mapping[str, Any]) -> GearEvaluation:
        return GearEvaluation(
            verdict="speculative",
            score=50.0,
            reasons=["scaffold adapter has no gear scoring data yet"],
            components=[ScoreComponent("placeholder", 5.0, 10, LABEL_HEURISTIC, "no starter data")],
        )

    def score_team(
        self, member_keys: Sequence[str], context: Mapping[str, Any]
    ) -> list[ScoreComponent]:
        return [
            ScoreComponent(
                "team_synergy",
                5.0,
                10,
                LABEL_HEURISTIC,
                "scaffold adapter has no character metadata yet — neutral fit",
            )
        ]
'''

_TERMINOLOGY_TEMPLATE = '''{
  "_meta": {
    "review": "hand_curated",
    "notes": "EDIT ME FIRST: the chat model learns the game from this table. Contract tests require the keys listed in core/games/terminology.py."
  },
  "terms": {
    "character": {"display": "Character", "gloss": "Playable unit you own and level"},
    "character_plural": {"display": "Characters", "gloss": ""},
    "equipment": {"display": "Weapon", "gloss": "Signature weapon; rename me"},
    "equipment_plural": {"display": "Weapons", "gloss": ""},
    "gear": {"display": "Gear piece", "gloss": "Set-based gear piece; rename me"},
    "gear_plural": {"display": "Gear pieces", "gloss": ""},
    "duplication": {"display": "Dupes", "gloss": "Dupe system 0-6; rename me"},
    "special_progression": {"display": "Skill track", "gloss": "Per-character progression; rename me"},
    "team": {"display": "Team", "gloss": "Characters fighting together"},
    "build": {"display": "Build", "gloss": "Equipment + gear loadout"},
    "role": {"display": "Role", "gloss": "Combat role; rename me"},
    "attribute": {"display": "Attribute", "gloss": "Element/attribute; rename me"},
    "pull_currency": {"display": "Pull currency", "gloss": "Premium currency for pulls; rename me"}
  }
}
'''

_PROMPT_TEMPLATE = '''Extract the visible values from this {title} character overview screen.

Use null for anything you cannot read confidently — never guess.
Map the game's on-screen labels onto: character_name, level, duplication_level.
'''


def scaffold_new_game(game_id: str, games_root: Path) -> Path:
    if not game_id.isidentifier() or game_id != game_id.lower():
        raise ValidationError(
            f"'{game_id}' is not a valid game id (lowercase letters/digits/underscore)"
        )
    target = games_root / game_id
    if target.exists():
        raise ValidationError(f"game '{game_id}' already exists at {target}")

    class_name = "".join(part.capitalize() for part in game_id.split("_"))
    title = game_id.replace("_", " ").upper()

    (target / "data").mkdir(parents=True)
    (target / "prompts").mkdir()
    (target / "__init__.py").write_text(
        _REGISTRY_INIT.format(title=title), encoding="utf-8"
    )
    (target / "adapter.py").write_text(
        _ADAPTER_TEMPLATE.format(game_id=game_id, class_name=class_name, title=title),
        encoding="utf-8",
    )
    (target / "screenshot_schemas.py").write_text(
        '"""Screenshot candidate schemas (scaffold placeholder)."""\n',
        encoding="utf-8",
    )
    (target / "data" / "terminology.json").write_text(
        _TERMINOLOGY_TEMPLATE, encoding="utf-8"
    )
    (target / "prompts" / "character_overview.md").write_text(
        _PROMPT_TEMPLATE.format(title=title), encoding="utf-8"
    )
    return target


def register_installed(game_id: str, games_root: Path) -> Path:
    registry_file = games_root / "installed.json"
    data = {"adapters": {}}
    if registry_file.exists():
        import json

        data = json.loads(registry_file.read_text(encoding="utf-8"))
    data.setdefault("adapters", {})[game_id] = (
        f"game_companion.games.{game_id}.adapter:"
        + "".join(part.capitalize() for part in game_id.split("_"))
        + "Adapter"
    )
    import json

    registry_file.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return registry_file
