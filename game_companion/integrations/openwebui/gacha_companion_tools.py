"""Open WebUI Tools integration for Gacha Companion.

This file is deliberately THIN: it only translates Open WebUI tool calls into
HTTP calls against the local Gacha Companion service (default
http://127.0.0.1:8765). No business logic lives here.

Install (Open WebUI):
1. Start the companion:  `game-companion serve`
2. In Open WebUI: Settings -> Tools -> import this file, or Workspace -> Tools
   -> new tool, pasting this file's contents.
3. In a chat, enable the "Gacha Companion" tool. Ask account questions like
   "What is my Burnice running?" or type `#CODES` for redeem codes.

The tool descriptions below are part of the product: they tell the model WHEN
to retrieve authoritative state before answering account-specific questions.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import requests
from pydantic import BaseModel, Field


class Tools:
    class Valves(BaseModel):
        base_url: str = Field(
            default="http://127.0.0.1:8765",
            description="Base URL of the local Gacha Companion service.",
        )
        game_id: str = Field(default="zzz", description="Active game id (e.g. zzz).")
        player_id: str = Field(
            default="",
            description="Player profile id. Leave empty to use the only existing profile.",
        )

    def __init__(self) -> None:
        self.valves = self.Valves()
        self.citations = False

    # ------------------------------------------------------------------ util

    def _player_param(self) -> str:
        return f"?player_id={self.valves.player_id}" if self.valves.player_id else ""

    def _call(self, __event_call: Callable | None, method: str, path: str, body: dict | None = None) -> str:
        url = f"{self.valves.base_url.rstrip('/')}/api{path}"
        try:
            response = requests.request(method, url, json=body, timeout=60)
            if response.status_code >= 400:
                try:
                    detail = response.json().get("detail", response.text)
                except ValueError:
                    detail = response.text
                if response.status_code == 404 and "no unique player profile" in str(detail):
                    return self._profile_hint()
                return f"Error {response.status_code}: {detail}"
            try:
                return json.dumps(response.json(), ensure_ascii=False)
            except ValueError:
                return response.text  # markdown endpoints
        except requests.RequestException as exc:
            return f"Gacha Companion service unreachable at {self.valves.base_url}: {exc}"

    def _profile_hint(self) -> str:
        """Translate the 'no unique player profile' error into a fix the model
        can relay: list the existing profiles and name the valve to set."""
        base = self.valves.base_url.rstrip("/")
        players = []
        try:
            r = requests.get(f"{base}/api/players", timeout=10)
            if r.status_code == 200:
                players = r.json().get("players", [])
        except requests.RequestException:
            pass
        if not players:
            return (
                "Error 404: no player profile exists yet. Create one with the setup "
                f"wizard (bash setup.sh), or: curl -X POST {base}/api/players "
                '-H \'Content-Type: application/json\' -d \'{"display_name":"YourName"}\''
            )
        lines = [
            "Error 404: more than one player profile exists, so the tool's "
            "player_id valve must say which one to use. Existing profiles:"
        ]
        lines += [f"- {p['display_name']}: {p['id']}" for p in players]
        lines.append(
            "Ask the user which profile is theirs, then have them open the Gacha "
            "Companion tool in Workspace -> Tools, open Valves (gear icon), and "
            "paste that id into player_id."
        )
        return "\n".join(lines)

    def _game(self) -> str:
        return self.valves.game_id

    # ---------------------------------------------------------------- tools

    def get_player_profile(self, __event_call: Callable | None = None) -> str:
        """Return the stored player profile. Call this before account-specific
        answers when you need to know who the player is."""
        return self._call(__event_call, "GET", f"/games/{self._game()}/characters{self._player_param()}")

    def list_characters(
        self, owned_only: bool = True, __event_call: Callable | None = None
    ) -> str:
        """List the player's characters (e.g. ZZZ Agents) with levels, skills and
        Mindscape/duplication info. ALWAYS call this before roster or team
        questions so advice uses the real roster, not guesses."""
        suffix = f"{self._player_param()}&owned={str(owned_only).lower()}" if self.valves.player_id else f"?owned={str(owned_only).lower()}"
        return self._call(__event_call, "GET", f"/games/{self._game()}/characters{suffix}")

    def get_character(self, character: str, __event_call: Callable | None = None) -> str:
        """Get full stored data for one character by name or key (e.g. 'burnice'):
        level, Mindscape, skills, builds, equipment and gear. Call this whenever
        the user asks what a specific character is running or has."""
        return self._call(__event_call, "GET", f"/games/{self._game()}/characters/{character}{self._player_param()}")

    def update_character(
        self, character: str, fields: dict[str, Any], __event_call: Callable | None = None
    ) -> str:
        """Update stored character fields after the user states a change (level,
        Mindscape/duplication, favorite, notes, game-specific data). Use when
        the user says things like 'my X is now Mindscape 2'."""
        return self._call(__event_call, "PATCH", f"/games/{self._game()}/characters/{character}{self._player_param()}", fields)

    def get_build(self, character: str, __event_call: Callable | None = None) -> str:
        """Get the character's saved builds including the ACTIVE build (equipment +
        per-slot gear). Use for 'what is my X running?' questions."""
        return self._call(__event_call, "GET", f"/games/{self._game()}/characters/{character}{self._player_param()}")

    def update_build(
        self, character: str, build_updates: dict[str, Any], __event_call: Callable | None = None
    ) -> str:
        """Update a build: set equipment_item_id, gear slots ({slot: gear_item_id}),
        notes, or activate a build. Ask for confirmation of details when unclear."""
        char = json.loads(self.get_character(character, __event_call))
        builds = char.get("builds") or []
        if not builds:
            return f"No build exists for {character} yet; create one via the API first."
        build_id = builds[0]["id"]
        return self._call(__event_call, "PATCH", f"/games/{self._game()}/characters/{character}/builds/{build_id}{self._player_param()}", build_updates)

    def list_equipment(self, character: str | None = None, __event_call: Callable | None = None) -> str:
        """List stored weapon-like equipment (ZZZ: W-Engines), optionally filtered
        to one character. Use for equipment/inventory questions."""
        query = f"character={character}" if character else ""
        prefix = self._player_param().lstrip("?")
        joiner = "&" if prefix and query else ("?" if prefix or query else "")
        return self._call(__event_call, "GET", f"/games/{self._game()}/equipment{joiner}{prefix}{query}")

    def get_resources(self, __event_call: Callable | None = None) -> str:
        """List tracked upgrade resources with deterministic status (done / prep /
        very_low / critically_low / unknown) and the calculation explanation.
        Use for 'can I afford to max X?' style questions."""
        return self._call(__event_call, "GET", f"/games/{self._game()}/resources{self._player_param()}")

    def update_resource(
        self, resource_key: str, quantity: int, __event_call: Callable | None = None
    ) -> str:
        """Set the stored quantity of an upgrade resource after the user reports a
        new amount (e.g. 'I have 420 drive discs exp')."""
        return self._call(__event_call, "PUT", f"/games/{self._game()}/resources/{resource_key}{self._player_param()}", {"quantity": quantity})

    def list_teams(self, __event_call: Callable | None = None) -> str:
        """List saved teams with members and active flags. Call before team advice
        to see which characters are already committed to active teams."""
        return self._call(__event_call, "GET", f"/games/{self._game()}/teams{self._player_param()}")

    def save_team(
        self, name: str, members: list[dict[str, Any]], is_active: bool = False,
        __event_call: Callable | None = None,
    ) -> str:
        """Save (or replace) a named team. members: [{'character': '<key or name>',
        'role': optional}]. Set is_active=true for endgame-allocated teams —
        activation fails if a character is already on another active team."""
        return self._call(__event_call, "POST", f"/games/{self._game()}/teams{self._player_param()}", {"name": name, "members": members, "is_active": is_active})

    def list_gear(
        self, character: str | None = None, __event_call: Callable | None = None
    ) -> str:
        """List stored gear pieces (ZZZ: Drive Discs), optionally for one character.
        Use for gear/inventory questions."""
        query = f"character={character}" if character else ""
        prefix = self._player_param().lstrip("?")
        joiner = "&" if prefix and query else ("?" if prefix or query else "")
        return self._call(__event_call, "GET", f"/games/{self._game()}/gear{joiner}{prefix}{query}")

    def add_gear(
        self, gear: dict[str, Any], __event_call: Callable | None = None
    ) -> str:
        """Record a new gear piece (set, slot, main stat, substats, level). Only add
        gear the user explicitly described or that came from a confirmed import."""
        return self._call(__event_call, "POST", f"/games/{self._game()}/gear{self._player_param()}", gear)

    def favorite_gear(
        self, gear_id: str, favorite: bool = True, __event_call: Callable | None = None
    ) -> str:
        """Mark a gear piece as favorite (or unmark). Use when the user says 'keep
        this disc' / 'lock this one' semantics apply to favorites."""
        return self._call(__event_call, "PATCH", f"/games/{self._game()}/gear/{gear_id}{self._player_param()}", {"favorite": favorite})

    def search_game_sources(
        self, question: str, __event_call: Callable | None = None
    ) -> str:
        """Research a current game question across trusted registered sources with
        citations. Use for patch-sensitive, mechanics or meta questions instead of
        answering from memory. Requires search+LLM configuration."""
        return self._call(__event_call, "POST", f"/games/{self._game()}/research/query{self._player_param()}", {"question": question})

    def get_active_codes(self, __event_call: Callable | None = None) -> str:
        """Get tracked redeem codes for the current game. ALWAYS call this when the
        user types '#CODES' or asks for redeem codes. Used codes are marked."""
        return self._call(__event_call, "GET", f"/games/{self._game()}/codes.md{self._player_param()}")

    def mark_code_used(self, code_id: str, __event_call: Callable | None = None) -> str:
        """Mark a redeem code as used by this player (it will render struck through)."""
        return self._call(__event_call, "POST", f"/games/{self._game()}/codes/{code_id}/mark-used{self._player_param()}")

    def record_combat_result(
        self, result: dict[str, Any], __event_call: Callable | None = None
    ) -> str:
        """Record a combat/endgame attempt (encounter_key, cleared, stars, score,
        team_id...). Use when the user reports a clear/fail in an endgame mode."""
        return self._call(__event_call, "POST", f"/games/{self._game()}/combat-results{self._player_param()}", result)

    def get_combat_history(self, encounter: str | None = None, __event_call: Callable | None = None) -> str:
        """Get combat history trends (win rate, by team/encounter, improvement).
        Use for performance/progress questions."""
        query = f"?encounter={encounter}" if encounter else ""
        return self._call(__event_call, "GET", f"/games/{self._game()}/combat-results/trends{self._player_param()}{query}")

    def record_training_issue(
        self, category: str, description: str, character_keys: list[str] | None = None,
        __event_call: Callable | None = None,
    ) -> str:
        """Record (or increment) a player weakness/issue, e.g. 'swap timing' or
        'rotation drops buff'. Use when the user mentions what they did wrong or
        find difficult, so future tutoring can adapt."""
        return self._call(__event_call, "POST", f"/games/{self._game()}/training/issues{self._player_param()}", {
            "category": category,
            "description": description,
            "character_keys": character_keys or [],
        })

    def get_training_focus(self, __event_call: Callable | None = None) -> str:
        """Get the player's open training issues. ALWAYS call this before giving
        rotations or execution advice so explanations can adapt to known
        weaknesses."""
        return self._call(__event_call, "GET", f"/games/{self._game()}/training/focus{self._player_param()}")

    def recommend_teams(
        self, encounter: str | None = None, __event_call: Callable | None = None
    ) -> str:
        """Account-aware team recommendations from the real roster, builds and
        preferences. Use for 'who should X partner with?' — combine with
        get_character for the character in question."""
        body: dict[str, Any] = {}
        if encounter:
            body["encounter"] = encounter
        return self._call(__event_call, "POST", f"/games/{self._game()}/recommendations/teams{self._player_param()}", body)

    def evaluate_gear_inventory(self, __event_call: Callable | None = None) -> str:
        """Evaluate stored gear: best pieces per character and safe-to-discard
        candidates. Use for 'which discs should I keep?' questions."""
        return self._call(__event_call, "POST", f"/games/{self._game()}/recommendations/gear-inventory{self._player_param()}")

    def get_upgrade_plan(self, __event_call: Callable | None = None) -> str:
        """Get the account-wide upgrade/farming priority plan with reasons. Use for
        'what should I farm next?' questions."""
        return self._call(__event_call, "POST", f"/games/{self._game()}/recommendations/plan{self._player_param()}")
