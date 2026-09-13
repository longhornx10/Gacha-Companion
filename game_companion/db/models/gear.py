"""Gear: individual equippable pieces (ZZZ Drive Discs, HSR Relics...)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from game_companion.db.base import Base, PKMixin, TimestampMixin, UTCDateTime


class GearItem(PKMixin, TimestampMixin, Base):
    __tablename__ = "gear_items"

    game_id: Mapped[str] = mapped_column(String(40), index=True)
    player_profile_id: Mapped[str] = mapped_column(
        ForeignKey("player_profiles.id", ondelete="CASCADE"), index=True
    )
    set_key: Mapped[str | None] = mapped_column(String(80), default=None)
    slot: Mapped[str | None] = mapped_column(String(20), default=None)
    rarity: Mapped[int | None] = mapped_column(Integer, default=None)
    level: Mapped[int | None] = mapped_column(Integer, default=None)
    main_stat_key: Mapped[str | None] = mapped_column(String(40), default=None)
    main_stat_value: Mapped[float | None] = mapped_column(Float, default=None)
    # List of {"key": str, "value": float, "rolls": int | None} entries.
    substats: Mapped[list] = mapped_column(JSON, default=list)
    locked: Mapped[bool] = mapped_column(Boolean, default=False)
    favorite: Mapped[bool] = mapped_column(Boolean, default=False)
    equipped_character_id: Mapped[str | None] = mapped_column(
        ForeignKey("characters.id", ondelete="SET NULL"), index=True, default=None
    )
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    source: Mapped[str] = mapped_column(String(40), default="manual")
    last_verified_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), default=None)
