"""Team service: adapter-validated team integrity.

Rules (deterministic):
- Team size must be within the adapter's ``TeamRules`` (e.g. ZZZ: exactly 3).
- A character appears at most once per team.
- A character can belong to at most one *active* team (simultaneous allocation
  exclusion). Activation conflicts are reported, never silently resolved.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy.orm import Session

from game_companion.core.games.base import GameAdapter
from game_companion.db.models import Character, Team
from game_companion.db.repositories import CharacterRepository, TeamRepository
from game_companion.errors import ConflictError, ValidationError


class TeamService:
    def __init__(self, session: Session, adapter: GameAdapter) -> None:
        self.session = session
        self.adapter = adapter
        self.teams = TeamRepository(session)
        self.characters = CharacterRepository(session)

    def _resolve_member(self, game_id: str, player_id: str, ref: str) -> Character:
        char = self.characters.get(ref)
        if char is not None and char.game_id == game_id and char.player_profile_id == player_id:
            return char
        return self.characters.get_by_key_or_raise(game_id, player_id, ref)

    def save_team(
        self,
        game_id: str,
        player_id: str,
        name: str,
        members: Sequence[Mapping[str, Any]],
        *,
        notes: str | None = None,
        is_active: bool | None = None,
    ) -> Team:
        rules = self.adapter.team_rules()
        n = len(members)
        if not (rules.min_size <= n <= rules.max_size):
            term = self.adapter.terminology()
            raise ValidationError(
                f"a {term.team} for '{self.adapter.display_name}' needs "
                f"{rules.min_size}..{rules.max_size} {term.character_plural}, got {n}"
            )
        team = self.teams.find_by_name(game_id, player_id, name)
        if team is None:
            team = Team(game_id=game_id, player_profile_id=player_id, name=name)
            self.teams.add(team)
        team.notes = notes if notes is not None else team.notes

        seen: set[str] = set()
        resolved: list[tuple[Character, int, str | None]] = []
        for i, member in enumerate(members):
            ref = str(member.get("character") or member.get("character_id") or "").strip()
            if not ref:
                raise ValidationError(f"team member #{i + 1} is missing 'character'")
            char = self._resolve_member(game_id, player_id, ref)
            if char.id in seen:
                raise ValidationError(f"character '{char.display_name}' listed twice in team '{name}'")
            seen.add(char.id)
            resolved.append((char, int(member.get("position", i)), member.get("role")))

        self.teams.clear_members(team.id)
        for char, position, role in resolved:
            self.teams.set_member(team.id, char.id, position, role)

        if is_active is not None:
            if is_active:
                self.activate_team(team)
            else:
                team.is_active = False
        self.session.flush()
        return team

    def activate_team(self, team: Team) -> dict:
        conflicts: list[str] = []
        for active in self.teams.active_teams(team.game_id, team.player_profile_id):
            if active.id == team.id:
                continue
            overlap = {m.character_id for m in team.members} & {
                m.character_id for m in active.members
            }
            for character_id in overlap:
                char = self.characters.get(character_id)
                name = char.display_name if char else character_id
                conflicts.append(f"'{name}' is already on active team '{active.name}'")
        if conflicts:
            raise ConflictError(
                f"cannot activate team '{team.name}': {'; '.join(conflicts)}"
            )
        team.is_active = True
        self.session.flush()
        return {"team_id": team.id, "active": True}
