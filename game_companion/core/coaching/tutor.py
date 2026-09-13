"""Combat tutor (M7): deterministic context assembly + LLM rendering.

The tutor gathers authoritative state (character, build, gear, training
history, research claims, preferences) itself, then asks the LLM to explain.
Without a configured LLM it returns the assembled context with a clear error,
never a fabricated explanation.
"""

from __future__ import annotations

from typing import Any, Protocol

from sqlalchemy.orm import Session

from game_companion.api.serialize import build_dict, character_dict
from game_companion.core.coaching.training import TrainingService
from game_companion.core.games.base import GameAdapter
from game_companion.core.roster.service import RosterService
from game_companion.db.repositories import PlayerRepository, ResearchRepository
from game_companion.errors import LLMNotConfiguredError

MODE_GUIDANCE = {
    "simple": (
        "Assume the player is new. Avoid unexplained jargon: every game term must be "
        "defined in one plain sentence before it is used. Keep sentences short."
    ),
    "advanced": (
        "You may use standard game terminology freely, but stay accurate and cite the "
        "source claims provided when making build/mechanics statements."
    ),
    "button_by_button": (
        "Produce a numbered, step-by-step rotation. Each step: the input/ability name, "
        "why it happens, and what to watch for. Prefer simple inputs if the player's "
        "preferences say they dislike high-execution sequences."
    ),
}


class CompleteFn(Protocol):
    def complete(self, messages: list[dict], *, temperature: float = 0.4) -> str: ...


def build_tutor_context(
    session: Session,
    adapter: GameAdapter,
    game_id: str,
    player_id: str,
    character_key: str,
) -> dict[str, Any]:
    roster = RosterService(session, adapter)
    char = roster.resolve_character(game_id, player_id, character_key)
    build = roster.active_build(char)
    claims = ResearchRepository(session).claims(game_id, subject=char.key)
    issues = TrainingService(session).open_issues(game_id, player_id, char.key)
    preferences = {
        p.key: p.value
        for p in PlayerRepository(session).list_preferences(player_id)
        if p.scope in ("global", game_id)
    }
    return {
        "character": character_dict(char),
        "active_build": build_dict(build) if build else None,
        "research_claims": [
            {"claim_type": c.claim_type, "content": c.content, "evidence": c.evidence}
            for c in claims[:8]
        ],
        "training_issues": [
            {"category": i.category, "description": i.description, "occurrences": i.occurrences}
            for i in issues
        ],
        "preferences": preferences,
        "terminology": {
            "character": adapter.terminology().character,
            "equipment": adapter.terminology().equipment,
            "gear": adapter.terminology().gear,
            "duplication": adapter.terminology().duplication,
            "special_progression": adapter.terminology().special_progression,
        },
        "tutor_notes": adapter.tutor_notes(),
    }


def explain(
    session: Session,
    adapter: GameAdapter,
    game_id: str,
    player_id: str,
    *,
    character_key: str,
    topic: str,
    mode: str,
    persona_fragment: str,
    llm,
) -> dict:
    if not getattr(llm, "configured", False):
        raise LLMNotConfiguredError()
    if mode not in MODE_GUIDANCE:
        mode = "simple"
    context = build_tutor_context(session, adapter, game_id, player_id, character_key)
    import json

    context_json = json.dumps(context, ensure_ascii=False, default=str)
    system = (
        persona_fragment
        + "\nYou are a game mechanics tutor. Ground every statement in the provided "
        "account context. If a requested fact is not in the context, say you don't "
        "have it stored rather than inventing it. Use the research_claims only as "
        "labeled information (their claim_type tells you how established they are)."
        + "\n" + MODE_GUIDANCE[mode]
    )
    user = (
        f"Topic: {topic}. Game: {adapter.display_name}. "
        f"Teach it for the character below.\n\nACCOUNT CONTEXT (authoritative):\n{context_json}"
    )
    text = llm.complete(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0.4,
    )
    return {
        "explanation": text,
        "mode": mode,
        "topic": topic,
        "context_used": context,
    }
