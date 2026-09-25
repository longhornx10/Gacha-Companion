"""Equipment (weapon-like) and gear (piece) services."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy.orm import Session

from game_companion.core.games.base import GameAdapter
from game_companion.db.models import EquipmentItem, GearItem
from game_companion.db.repositories import (
    CharacterRepository,
    EquipmentRepository,
    GearRepository,
)
from game_companion.errors import ValidationError
from game_companion.utils import utcnow

_EQUIP_FIELDS = ("rarity", "level", "refinement", "locked", "notes", "data")
_GEAR_FIELDS = (
    "gear_type",
    "set_key",
    "slot",
    "rarity",
    "level",
    "main_stat_key",
    "main_stat_value",
    "substats",
    "locked",
    "favorite",
    "notes",
    "data",
)


def _validate_ref(
    characters: CharacterRepository, game_id: str, player_id: str, character_ref: str | None
):
    if character_ref is None:
        return None
    char = characters.get(character_ref)
    if char is not None and char.game_id == game_id and char.player_profile_id == player_id:
        return char
    return characters.get_by_key_or_raise(game_id, player_id, character_ref)


class EquipmentService:
    def __init__(self, session: Session, adapter: GameAdapter) -> None:
        self.session = session
        self.adapter = adapter
        self.equipment = EquipmentRepository(session)
        self.characters = CharacterRepository(session)

    def create(self, game_id: str, player_id: str, payload: Mapping[str, Any]) -> EquipmentItem:
        key = str(payload.get("key") or "").strip()
        display_name = str(payload.get("display_name") or "").strip()
        if not key or not display_name:
            raise ValidationError("equipment requires 'key' and 'display_name'")
        char = _validate_ref(self.characters, game_id, player_id, payload.get("character"))
        item = EquipmentItem(
            game_id=game_id,
            player_profile_id=player_id,
            key=key,
            display_name=display_name,
            equipped_character_id=char.id if char else None,
            last_verified_at=utcnow() if payload.get("verified") else None,
            source=str(payload.get("source") or "manual"),
        )
        self._apply_fields(item, payload)
        return self.equipment.add(item)

    def update(self, item: EquipmentItem, payload: Mapping[str, Any]) -> EquipmentItem:
        if payload.get("unset_character"):
            payload = {**payload, "character": None, "unset_character": None}
        if "character" in payload:
            char = _validate_ref(
                self.characters, item.game_id, item.player_profile_id, payload.get("character")
            )
            # A character equips one item at a time: unequip their previous one.
            if char is not None:
                for other in self.equipment.equipped_by(char.id):
                    if other.id != item.id:
                        other.equipped_character_id = None
            item.equipped_character_id = char.id if char else None
        if payload.get("verified"):
            item.last_verified_at = utcnow()
        if "source" in payload and payload["source"]:
            item.source = payload["source"]
        self._apply_fields(item, payload)
        self.session.flush()
        return item

    def _apply_fields(self, item: EquipmentItem, payload: Mapping[str, Any]) -> None:
        for attr in _EQUIP_FIELDS:
            if attr in payload and payload[attr] is not None:
                setattr(item, attr, payload[attr])


class GearService:
    def __init__(self, session: Session, adapter: GameAdapter) -> None:
        self.session = session
        self.adapter = adapter
        self.gear = GearRepository(session)
        self.characters = CharacterRepository(session)

    def create(self, game_id: str, player_id: str, payload: Mapping[str, Any]) -> GearItem:
        char = _validate_ref(self.characters, game_id, player_id, payload.get("character"))
        slot = payload.get("slot")
        if slot is not None:
            valid = {s.key for s in self.adapter.gear_slots()}
            if slot not in valid:
                raise ValidationError(f"unknown gear slot '{slot}' (valid: {sorted(valid)})")
        families = self.adapter.gear_families()
        gear_type = payload.get("gear_type")
        if families:
            family_keys = {f.key for f in families}
            if gear_type is None:
                gear_type = families[0].key
            elif gear_type not in family_keys:
                raise ValidationError(
                    f"unknown gear family '{gear_type}' (valid: {sorted(family_keys)})"
                )
        item = GearItem(
            game_id=game_id,
            player_profile_id=player_id,
            gear_type=gear_type or "disc",
            equipped_character_id=char.id if char else None,
            last_verified_at=utcnow() if payload.get("verified") else None,
            source=str(payload.get("source") or "manual"),
        )
        self._apply_fields(item, payload)
        return self.gear.add(item)

    def update(self, item: GearItem, payload: Mapping[str, Any]) -> GearItem:
        if payload.get("unset_character"):
            payload = {**payload, "character": None, "unset_character": None}
        if "slot" in payload and payload["slot"] is not None:
            valid = {s.key for s in self.adapter.gear_slots()}
            if payload["slot"] not in valid:
                raise ValidationError(f"unknown gear slot '{payload['slot']}'")
        if "character" in payload:
            char = _validate_ref(
                self.characters, item.game_id, item.player_profile_id, payload.get("character")
            )
            item.equipped_character_id = char.id if char else None
        if payload.get("verified"):
            item.last_verified_at = utcnow()
        if "source" in payload and payload["source"]:
            item.source = payload["source"]
        self._apply_fields(item, payload)
        self.session.flush()
        return item

    def _apply_fields(self, item: GearItem, payload: Mapping[str, Any]) -> None:
        for attr in _GEAR_FIELDS:
            if attr in payload and payload[attr] is not None:
                setattr(item, attr, payload[attr])
