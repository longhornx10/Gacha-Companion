"""Persona schema.

A persona shapes *tone only* — never stored facts, calculations, citations or
validation. Personas live in ``<data_dir>/personas/*.json``; switching personas
never touches game state.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class PersonaConfig(BaseModel):
    id: str = Field(description="stable slug, e.g. 'calm_tactician'")
    name: str
    description: str = ""
    tone: str = "friendly"  # friendly | energetic | calm | playful | formal ...
    verbosity: str = "medium"  # low | medium | high
    style_traits: list[str] = Field(default_factory=list)
    example_phrases: list[str] = Field(default_factory=list)
    # Extra system-prompt preamble injected verbatim before game context.
    system_preamble: str = ""
    # Optional game binding ("zzz"); None = usable for any game.
    bound_game: str | None = None
    # Role-play mode: speak AS this character (catalog key + display name).
    # Tone rules still apply to facts — the character never invents data.
    role_as_character: str | None = None
    role_as_name: str | None = None

    def system_prompt_fragment(self, terminology_line: str = "") -> str:
        if self.role_as_character:
            who = self.role_as_name or self.role_as_character
            parts = [
                f"You are role-playing as {who} while helping the user with their "
                f"gacha game. Stay in character: speak the way {who} would, with "
                f"that personality and those mannerisms.",
                f"Persona framing: '{self.name}' (tone: {self.tone}, verbosity: {self.verbosity}).",
            ]
        else:
            parts = [
                f"You are the user's gacha companion, speaking with a '{self.name}' persona "
                f"(tone: {self.tone}, verbosity: {self.verbosity}).",
            ]
        if self.description:
            parts.append(self.description)
        if self.style_traits:
            parts.append("Style traits: " + "; ".join(self.style_traits) + ".")
        if self.example_phrases:
            parts.append("Phrasing examples (mimic the vibe, do not copy literally):")
            parts.extend(f"  - {p}" for p in self.example_phrases)
        if terminology_line:
            parts.append(terminology_line)
        parts.append(
            "The persona influences TONE ONLY. Never alter facts, numbers, citations, "
            "or recommendations to fit the persona."
            + (
                " Even in character, only state game facts backed by tool results — "
                "the character never invents data about the user's account."
                if self.role_as_character
                else ""
            )
        )
        if self.system_preamble:
            parts.append(self.system_preamble)
        return "\n".join(parts)
