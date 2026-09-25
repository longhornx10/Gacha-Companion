"""Roster + build services (game-agnostic; adapter validates specifics)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy.orm import Session

from game_companion.core.games.base import GameAdapter
from game_companion.db.models import Character, CharacterBuild, GearItem
from game_companion.db.repositories import (
    BuildRepository,
    CharacterRepository,
    EquipmentRepository,
    GearRepository,
)
from game_companion.errors import ConflictError, ValidationError
from game_companion.utils import utcnow


class RosterService:
    def __init__(self, session: Session, adapter: GameAdapter) -> None:
        self.session = session
        self.adapter = adapter
        self.characters = CharacterRepository(session)
        self.builds = BuildRepository(session)
        self.gear = GearRepository(session)
        self.equipment = EquipmentRepository(session)

    # -- characters -----------------------------------------------------------

    def resolve_character(self, game_id: str, player_id: str, ref: str) -> Character:
        """Accept an id or a character key (adapter canonical key)."""
        char = self.characters.get(ref)
        if char is not None and char.game_id == game_id and char.player_profile_id == player_id:
            return char
        return self.characters.get_by_key_or_raise(game_id, player_id, ref)

    def create_character(self, game_id: str, player_id: str, payload: Mapping[str, Any]) -> Character:
        key = str(payload.get("key") or "").strip().lower()
        if not key:
            raise ValidationError("character 'key' is required (stable lowercase slug)")
        if self.characters.find_by_key(game_id, player_id, key) is not None:
            raise ConflictError(f"character '{key}' already exists for this player/game")
        data = self.adapter.validate_character_data(payload.get("data") or {})
        display_name = str(payload.get("display_name") or key.replace("_", " ").title())
        char = Character(
            game_id=game_id,
            player_profile_id=player_id,
            key=key,
            display_name=display_name,
            rarity=payload.get("rarity"),
            owned=bool(payload.get("owned", True)),
            level=payload.get("level"),
            duplication_level=payload.get("duplication_level"),
            favorite=bool(payload.get("favorite", False)),
            notes=payload.get("notes"),
            data=data,
            source=str(payload.get("source") or "manual"),
            last_verified_at=utcnow() if payload.get("verified") else None,
        )
        return self.characters.add(char)

    def update_character(self, char: Character, payload: Mapping[str, Any]) -> Character:
        updatable = (
            "display_name", "rarity", "owned", "level",
            "duplication_level", "favorite", "notes", "source",
        )
        for attr in updatable:
            if attr in payload:
                setattr(char, attr, payload[attr])
        if "data" in payload and payload["data"] is not None:
            merged = {**char.data, **dict(payload["data"])}
            char.data = self.adapter.validate_character_data(merged)
        if payload.get("verified"):
            char.last_verified_at = utcnow()
        self.session.flush()
        return char

    def set_skills(self, char: Character, skills: Mapping[str, int | None]) -> dict:
        definitions = {d.key: d for d in self.adapter.skill_definitions()}
        unknown = [k for k in skills if k not in definitions]
        if unknown:
            known = ", ".join(sorted(definitions))
            raise ValidationError(
                f"unknown skill key(s) {unknown} for game '{self.adapter.game_id}' "
                f"(known: {known})"
            )
        for skill_key, level in skills.items():
            max_level = definitions[skill_key].max_level
            if level is not None and not (0 <= level <= max_level):
                raise ValidationError(
                    f"skill '{skill_key}' level {level} outside 0..{max_level}"
                    + (f" ({definitions[skill_key].max_level_note})" if definitions[skill_key].max_level_note else "")
                )
            self.characters.set_skill(char.id, skill_key, level)
        return {k: v for k, v in skills.items()}

    # -- builds ---------------------------------------------------------------

    def create_build(
        self,
        char: Character,
        name: str = "default",
        *,
        notes: str | None = None,
        set_active: bool = False,
    ) -> CharacterBuild:
        existing = None
        for build in self.builds.for_character(char.id):
            if build.name == name:
                existing = build
                break
        if existing is not None:
            raise ConflictError(f"build '{name}' already exists for {char.display_name}")
        build = CharacterBuild(
            game_id=char.game_id,
            player_profile_id=char.player_profile_id,
            character_id=char.id,
            name=name,
            notes=notes,
        )
        self.builds.add(build)
        if set_active:
            self.activate_build(build)
        return build

    def active_build(self, char: Character) -> CharacterBuild | None:
        return self.builds.active_for_character(char.id)

    def set_build_equipment(self, build: CharacterBuild, equipment_item_id: str | None) -> CharacterBuild:
        if equipment_item_id is not None:
            item = self.equipment.get_or_raise(equipment_item_id, "equipment item")
            self._assert_belongs(item.game_id, item.player_profile_id, build)
            item.equipped_character_id = build.character_id
        elif build.equipment_item_id:
            old = self.equipment.get(build.equipment_item_id)
            if old is not None and old.equipped_character_id == build.character_id:
                old.equipped_character_id = None
        build.equipment_item_id = equipment_item_id
        self.session.flush()
        return build

    def set_build_slot(
        self, build: CharacterBuild, slot: str, gear_item_id: str | None
    ) -> dict:
        valid_slots = {s.key for s in self.adapter.gear_slots()}
        if slot not in valid_slots:
            raise ValidationError(f"unknown gear slot '{slot}' (valid: {sorted(valid_slots)})")
        moves: list[str] = []
        if gear_item_id is not None:
            item = self.gear.get_or_raise(gear_item_id, "gear item")
            self._assert_belongs(item.game_id, item.player_profile_id, build)
            self._claim_gear(item, build.character_id, moves)
        row = self.builds.set_slot(build.id, slot, gear_item_id)
        if build.is_active:
            self._sync_equipped_fields(build, moves)
        return {"slot": row.slot, "gear_item_id": row.gear_item_id, "moves": moves}

    def activate_build(self, build: CharacterBuild) -> dict:
        moves: list[str] = []
        for other in self.builds.for_character(build.character_id):
            if other.id != build.id:
                other.is_active = False
        build.is_active = True
        # Claim this build's gear, evicting it from other active builds.
        slot_rows = {row.slot: row for row in build.gear_slots}
        for slot in [s.key for s in self.adapter.gear_slots()]:
            row = slot_rows.get(slot)
            if row is not None and row.gear_item_id:
                item = self.gear.get(row.gear_item_id)
                if item is not None:
                    self._claim_gear(item, build.character_id, moves)
        self._sync_equipped_fields(build, moves)
        return {"build_id": build.id, "active": True, "moves": moves}

    # -- internals -------------------------------------------------------------

    def _assert_belongs(self, game_id: str, player_id: str, build: CharacterBuild) -> None:
        if game_id != build.game_id or player_id != build.player_profile_id:
            raise ValidationError("item belongs to a different player/game")

    def _claim_gear(self, item: GearItem, character_id: str, moves: list[str]) -> None:
        """Equip ``item`` to ``character``; record evictions it causes elsewhere."""
        item.equipped_character_id = character_id
        self._evict_from_other_active_builds(item, character_id, moves)

    def _evict_from_other_active_builds(
        self, item: GearItem, character_id: str, moves: list[str]
    ) -> None:
        from sqlalchemy import select

        from game_companion.db.models import BuildGearSlot

        rows = self.session.scalars(
            select(BuildGearSlot).where(BuildGearSlot.gear_item_id == item.id)
        ).all()
        for row in rows:
            build = self.builds.get(row.build_id)
            if build is None or not build.is_active or build.character_id == character_id:
                continue
            moves.append(
                f"gear '{item.id}' moved out of active build '{build.name}' slot '{row.slot}'"
            )
            row.gear_item_id = None
        self.session.flush()

    def _sync_equipped_fields(self, build: CharacterBuild, moves: list[str]) -> None:
        """Make equipped_character_id exactly match the active build's slots."""
        claimed = {row.gear_item_id for row in build.gear_slots if row.gear_item_id}
        # Unequip character's gear that is no longer in the active build.
        for item in self.gear.search(
            build.game_id, build.player_profile_id, equipped_character_id=build.character_id
        ):
            if item.id not in claimed:
                item.equipped_character_id = None
        for gear_id in claimed:
            item = self.gear.get(gear_id)
            if item is not None:
                item.equipped_character_id = build.character_id
        self.session.flush()


__all__ = ["RosterService"]
