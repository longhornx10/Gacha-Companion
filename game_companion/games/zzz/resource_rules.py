"""ZZZ resource definitions and threshold configuration.

Requirement numbers (X per character) are intentionally unknown (null): the
threshold evaluator returns ``unknown`` instead of inventing game facts. Fill
``data/resource_requirements.json`` (or a data_dir override) with verified
values to activate deterministic done/prep/low states.
"""

from __future__ import annotations

import json
from importlib import resources
from pathlib import Path

from game_companion.core.games.base import ResourceDefinition, ResourceThresholdConfig

RESOURCE_KEYS: list[tuple[str, str]] = [
    ("dennies", "Dennies"),
    ("agent_exp", "Agent EXP (Investigator Logs)"),
    ("wengine_exp", "W-Engine EXP (Energy Modules)"),
    ("drive_exp", "Drive Disc EXP (Plates)"),
    ("skill_material", "Skill upgrade materials"),
    ("core_skill_material", "Core Skill upgrade materials"),
    ("boss_material", "Boss ascension material"),
    ("weekly_material", "Weekly challenge material"),
]

_OVERLOADABLE = {
    "resource_requirements": "resource_requirements.json",
    "agents": "agents.json",
    "progression": "progression.json",
    "drive_disc_sets": "drive_disc_sets.json",
}


def load_data_json(name: str, overrides_dir: Path | None) -> dict:
    """Load a packaged ZZZ data file, optionally merged with a user override."""
    packaged = json.loads(
        resources.files("game_companion.games.zzz")
        .joinpath("data", _OVERLOADABLE[name])
        .read_text(encoding="utf-8")
    )
    if overrides_dir is not None:
        override_path = overrides_dir / _OVERLOADABLE[name]
        if override_path.exists():
            override = json.loads(override_path.read_text(encoding="utf-8"))
            for key, value in override.items():
                if not key.startswith("_"):
                    packaged[key] = value
    return packaged


def resource_definitions(requirements: dict) -> list[ResourceDefinition]:
    reqs = requirements.get("requirements", {})
    definitions = []
    for key, name in RESOURCE_KEYS:
        single_max = reqs.get(key)
        notes = None
        if single_max is None:
            notes = "single-character max unknown; supply verified data to enable status thresholds"
        definitions.append(
            ResourceDefinition(key=key, name=name, single_character_max=single_max, notes=notes)
        )
    return definitions


THRESHOLD_CONFIG = ResourceThresholdConfig(low_fraction=0.25)
