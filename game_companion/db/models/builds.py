"""Builds: a character's loadout (equipment + per-slot gear) with an active build."""

from __future__ import annotations

from sqlalchemy import JSON, Boolean, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from game_companion.db.base import Base, PKMixin, TimestampMixin


class CharacterBuild(PKMixin, TimestampMixin, Base):
    __tablename__ = "character_builds"
    __table_args__ = (UniqueConstraint("character_id", "name", name="uq_character_build_name"),)

    game_id: Mapped[str] = mapped_column(String(40), index=True)
    player_profile_id: Mapped[str] = mapped_column(
        ForeignKey("player_profiles.id", ondelete="CASCADE"), index=True
    )
    character_id: Mapped[str] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(80), default="default")
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    equipment_item_id: Mapped[str | None] = mapped_column(
        ForeignKey("equipment_items.id", ondelete="SET NULL"), default=None
    )
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    data: Mapped[dict] = mapped_column(JSON, default=dict)

    gear_slots: Mapped[list[BuildGearSlot]] = relationship(
        back_populates="build", cascade="all, delete-orphan", lazy="selectin"
    )


class BuildGearSlot(PKMixin, TimestampMixin, Base):
    __tablename__ = "build_gear_slots"
    __table_args__ = (UniqueConstraint("build_id", "slot", name="uq_build_slot"),)

    build_id: Mapped[str] = mapped_column(
        ForeignKey("character_builds.id", ondelete="CASCADE"), index=True
    )
    slot: Mapped[str] = mapped_column(String(20))
    gear_item_id: Mapped[str | None] = mapped_column(
        ForeignKey("gear_items.id", ondelete="SET NULL"), default=None
    )

    build: Mapped[CharacterBuild] = relationship(back_populates="gear_slots")
