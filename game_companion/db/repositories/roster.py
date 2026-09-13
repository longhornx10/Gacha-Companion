"""Repositories for profiles, preferences and roster."""

from __future__ import annotations

from sqlalchemy import select

from game_companion.db.models import Character, CharacterSkill, PlayerPreference, PlayerProfile
from game_companion.db.repositories.base import BaseRepository
from game_companion.errors import NotFoundError


class PlayerRepository(BaseRepository[PlayerProfile]):
    model = PlayerProfile

    def find_sole(self) -> PlayerProfile | None:
        profiles = self.list_all()
        return profiles[0] if len(profiles) == 1 else None

    def require_sole(self) -> PlayerProfile:
        profile = self.find_sole()
        if profile is None:
            raise NotFoundError(
                "no unique player profile: pass player_id explicitly or create exactly one profile"
            )
        return profile

    # preferences -------------------------------------------------------------

    def get_preference(self, player_id: str, scope: str, key: str) -> PlayerPreference | None:
        stmt = select(PlayerPreference).where(
            PlayerPreference.player_profile_id == player_id,
            PlayerPreference.scope == scope,
            PlayerPreference.key == key,
        )
        return self.session.scalars(stmt).first()

    def set_preference(self, player_id: str, scope: str, key: str, value) -> PlayerPreference:
        pref = self.get_preference(player_id, scope, key)
        if pref is None:
            pref = PlayerPreference(player_profile_id=player_id, scope=scope, key=key)
            self.session.add(pref)
        pref.value = value
        self.session.flush()
        return pref

    def list_preferences(self, player_id: str, scope: str | None = None) -> list[PlayerPreference]:
        stmt = (
            select(PlayerPreference)
            .where(PlayerPreference.player_profile_id == player_id)
            .order_by(PlayerPreference.scope, PlayerPreference.key)
        )
        if scope is not None:
            stmt = stmt.where(PlayerPreference.scope == scope)
        return list(self.session.scalars(stmt))


class CharacterRepository(BaseRepository[Character]):
    model = Character

    def find_by_key(self, game_id: str, player_id: str, key: str) -> Character | None:
        stmt = select(Character).where(
            Character.game_id == game_id,
            Character.player_profile_id == player_id,
            Character.key == key,
        )
        return self.session.scalars(stmt).first()

    def get_by_key_or_raise(self, game_id: str, player_id: str, key: str) -> Character:
        char = self.find_by_key(game_id, player_id, key)
        if char is None:
            raise NotFoundError(f"character '{key}' not found for game '{game_id}'")
        return char

    def search(
        self,
        game_id: str,
        player_id: str,
        *,
        owned: bool | None = None,
        favorite: bool | None = None,
    ) -> list[Character]:
        stmt = (
            select(Character)
            .where(Character.game_id == game_id, Character.player_profile_id == player_id)
            .order_by(Character.display_name)
        )
        if owned is not None:
            stmt = stmt.where(Character.owned == owned)
        if favorite is not None:
            stmt = stmt.where(Character.favorite == favorite)
        return list(self.session.scalars(stmt))

    # skills --------------------------------------------------------------

    def get_skill(self, character_id: str, skill_key: str) -> CharacterSkill | None:
        stmt = select(CharacterSkill).where(
            CharacterSkill.character_id == character_id,
            CharacterSkill.skill_key == skill_key,
        )
        return self.session.scalars(stmt).first()

    def set_skill(self, character_id: str, skill_key: str, level: int | None) -> CharacterSkill:
        skill = self.get_skill(character_id, skill_key)
        if skill is None:
            skill = CharacterSkill(character_id=character_id, skill_key=skill_key)
            self.session.add(skill)
        skill.level = level
        self.session.flush()
        return skill
