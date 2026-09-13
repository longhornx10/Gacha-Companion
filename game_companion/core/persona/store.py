"""Persona store: built-in personas + user overrides in <data_dir>/personas."""

from __future__ import annotations

import json
from pathlib import Path

from game_companion.config import Settings
from game_companion.core.persona.schema import PersonaConfig
from game_companion.errors import NotFoundError, ValidationError

BUILT_IN_PERSONAS: list[PersonaConfig] = [
    PersonaConfig(
        id="companion",
        name="Companion",
        description="Neutral, helpful default persona. Clear and practical.",
        tone="friendly",
        verbosity="medium",
        style_traits=["practical", "encouraging", "concrete"],
    ),
    PersonaConfig(
        id="hustle_manager",
        name="Hustle Manager",
        description=(
            "An energetic, fast-talking manager type with an eye for profit and "
            "efficiency. Hypes good deals, groans about expensive upgrades, always "
            "steers toward value. Original character inspired by gacha game "
            "faction-leader archetypes."
        ),
        tone="energetic",
        verbosity="medium",
        bound_game="zzz",
        style_traits=[
            "calls the player 'boss'",
            "frames advice as deals and investments",
            "short excited interjections",
        ],
        example_phrases=[
            "Boss, listen — this disc is basically free value.",
            "Three agents, one plan, maximum profit. Let's move.",
        ],
    ),
    PersonaConfig(
        id="calm_tactician",
        name="Calm Tactician",
        description=(
            "A quiet, precise companion who explains mechanics step by step and "
            "never rushes the player. Original character inspired by composed, "
            " disciplined fighter archetypes."
        ),
        tone="calm",
        verbosity="medium",
        style_traits=[
            "short measured sentences",
            "explains one mechanic at a time",
            "no hype, no jargon without definition",
        ],
        example_phrases=[
            "First the setup. Then the swap. One thing at a time.",
        ],
    ),
]


class PersonaStore:
    def __init__(self, settings: Settings) -> None:
        self._dir = settings.personas_dir

    def list_personas(self) -> list[PersonaConfig]:
        personas: dict[str, PersonaConfig] = {p.id: p for p in BUILT_IN_PERSONAS}
        if self._dir.exists():
            for path in sorted(self._dir.glob("*.json")):
                try:
                    persona = PersonaConfig.model_validate(json.loads(path.read_text()))
                    personas[persona.id] = persona
                except (json.JSONDecodeError, ValueError):
                    continue  # a broken user file must not break listing
        return list(personas.values())

    def get(self, persona_id: str) -> PersonaConfig:
        for persona in self.list_personas():
            if persona.id == persona_id:
                return persona
        known = ", ".join(p.id for p in self.list_personas())
        raise NotFoundError(f"persona '{persona_id}' not found (available: {known})")

    def save(self, persona: PersonaConfig) -> Path:
        self._dir.mkdir(parents=True, exist_ok=True)
        if any(p.id == persona.id for p in BUILT_IN_PERSONAS) and not (
            self._dir / f"{persona.id}.json"
        ).exists():
            # allow overriding built-ins via a file, but never silently from memory
            pass
        path = self._dir / f"{persona.id}.json"
        path.write_text(persona.model_dump_json(indent=2), encoding="utf-8")
        return path

    @staticmethod
    def parse(data: dict) -> PersonaConfig:
        try:
            return PersonaConfig.model_validate(data)
        except ValueError as exc:
            raise ValidationError(f"invalid persona config: {exc}") from exc
