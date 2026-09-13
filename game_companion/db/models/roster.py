"""Roster: characters (generic) and their per-skill progression rows."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from game_companion.db.base import Base, PKMixin, TimestampMixin, UTCDateTime


class Character(PKMixin, TimestampMixin, Base):
    __tablename__ = "characters"
    __table_args__ = (UniqueConstraint("game_id", "player_profile_id", "key", name="uq_character_key"),)

    game_id: Mapped[str] = mapped_column(String(40), index=True)
    player_profile_id: Mapped[str] = mapped_column(
        ForeignKey("player_profiles.id", ondelete="CASCADE"), index=True
    )
    key: Mapped[str] = mapped_column(String(80))
    display_name: Mapped[str] = mapped_column(String(120))
    rarity: Mapped[int | None] = mapped_column(Integer, default=None)
    owned: Mapped[bool] = mapped_column(Boolean, default=True)
    level: Mapped[int | None] = mapped_column(Integer, default=None)
    duplication_level: Mapped[int | None] = mapped_column(Integer, default=None)
    favorite: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    # Game-specific extras (adapter-validated), e.g. ZZZ attribute/specialty hints.
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    source: Mapped[str] = mapped_column(String(40), default="manual")
    last_verified_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), default=None)

    skills: Mapped[list[CharacterSkill]] = relationship(
        back_populates="character", cascade="all, delete-orphan", lazy="selectin"
    )


class CharacterSkill(PKMixin, TimestampMixin, Base):
    __tablename__ = "character_skills"
    __table_args__ = (UniqueConstraint("character_id", "skill_key", name="uq_character_skill"),)

    character_id: Mapped[str] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), index=True
    )
    skill_key: Mapped[str] = mapped_column(String(60))
    level: Mapped[int | None] = mapped_column(Integer, default=None)
    data: Mapped[dict] = mapped_column(JSON, default=dict)

    character: Mapped[Character] = relationship(back_populates="skills")
