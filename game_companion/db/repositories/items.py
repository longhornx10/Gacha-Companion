"""Repositories for equipment, gear, builds and teams."""

from __future__ import annotations

from sqlalchemy import select

from game_companion.db.models import (
    BuildGearSlot,
    CharacterBuild,
    EquipmentItem,
    GearItem,
    Team,
    TeamMember,
)
from game_companion.db.repositories.base import BaseRepository


class EquipmentRepository(BaseRepository[EquipmentItem]):
    model = EquipmentItem

    def search(self, game_id: str, player_id: str, **filters) -> list[EquipmentItem]:
        stmt = (
            select(EquipmentItem)
            .where(EquipmentItem.game_id == game_id, EquipmentItem.player_profile_id == player_id)
            .order_by(EquipmentItem.display_name)
        )
        for attr, value in filters.items():
            if value is not None:
                stmt = stmt.where(getattr(EquipmentItem, attr) == value)
        return list(self.session.scalars(stmt))

    def equipped_by(self, character_id: str) -> list[EquipmentItem]:
        return self.list_all(equipped_character_id=character_id)


class GearRepository(BaseRepository[GearItem]):
    model = GearItem

    def search(self, game_id: str, player_id: str, **filters) -> list[GearItem]:
        stmt = (
            select(GearItem)
            .where(GearItem.game_id == game_id, GearItem.player_profile_id == player_id)
            .order_by(GearItem.slot, GearItem.set_key)
        )
        for attr, value in filters.items():
            if value is not None:
                stmt = stmt.where(getattr(GearItem, attr) == value)
        return list(self.session.scalars(stmt))


class BuildRepository(BaseRepository[CharacterBuild]):
    model = CharacterBuild

    def for_character(self, character_id: str) -> list[CharacterBuild]:
        stmt = (
            select(CharacterBuild)
            .where(CharacterBuild.character_id == character_id)
            .order_by(CharacterBuild.name)
        )
        return list(self.session.scalars(stmt))

    def active_for_character(self, character_id: str) -> CharacterBuild | None:
        stmt = select(CharacterBuild).where(
            CharacterBuild.character_id == character_id, CharacterBuild.is_active.is_(True)
        )
        return self.session.scalars(stmt).first()

    def get_slot(self, build_id: str, slot: str) -> BuildGearSlot | None:
        stmt = select(BuildGearSlot).where(
            BuildGearSlot.build_id == build_id, BuildGearSlot.slot == slot
        )
        return self.session.scalars(stmt).first()

    def set_slot(self, build_id: str, slot: str, gear_item_id: str | None) -> BuildGearSlot:
        row = self.get_slot(build_id, slot)
        if row is None:
            row = BuildGearSlot(build_id=build_id, slot=slot)
            self.session.add(row)
        row.gear_item_id = gear_item_id
        self.session.flush()
        return row


class TeamRepository(BaseRepository[Team]):
    model = Team

    def find_by_name(self, game_id: str, player_id: str, name: str) -> Team | None:
        stmt = select(Team).where(
            Team.game_id == game_id, Team.player_profile_id == player_id, Team.name == name
        )
        return self.session.scalars(stmt).first()

    def active_teams(self, game_id: str, player_id: str) -> list[Team]:
        stmt = select(Team).where(
            Team.game_id == game_id, Team.player_profile_id == player_id, Team.is_active.is_(True)
        )
        return list(self.session.scalars(stmt))

    def set_member(self, team_id: str, character_id: str, position: int, role: str | None) -> TeamMember:
        stmt = select(TeamMember).where(
            TeamMember.team_id == team_id, TeamMember.character_id == character_id
        )
        member = self.session.scalars(stmt).first()
        if member is None:
            member = TeamMember(team_id=team_id, character_id=character_id)
            self.session.add(member)
        member.position = position
        member.role = role
        self.session.flush()
        return member

    def clear_members(self, team_id: str) -> None:
        for member in self.session.scalars(
            select(TeamMember).where(TeamMember.team_id == team_id)
        ):
            self.session.delete(member)
        self.session.flush()
