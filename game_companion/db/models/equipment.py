"""Equipment (weapon-like items, e.g. ZZZ W-Engines / HSR Light Cones)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from game_companion.db.base import Base, PKMixin, TimestampMixin, UTCDateTime


class EquipmentItem(PKMixin, TimestampMixin, Base):
    __tablename__ = "equipment_items"

    game_id: Mapped[str] = mapped_column(String(40), index=True)
    player_profile_id: Mapped[str] = mapped_column(
        ForeignKey("player_profiles.id", ondelete="CASCADE"), index=True
    )
    key: Mapped[str] = mapped_column(String(80))
    display_name: Mapped[str] = mapped_column(String(160))
    rarity: Mapped[int | None] = mapped_column(Integer, default=None)
    level: Mapped[int | None] = mapped_column(Integer, default=None)
    # Star/refinement level, semantics defined by the game adapter.
    refinement: Mapped[int | None] = mapped_column(Integer, default=None)
    equipped_character_id: Mapped[str | None] = mapped_column(
        ForeignKey("characters.id", ondelete="SET NULL"), index=True, default=None
    )
    locked: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    source: Mapped[str] = mapped_column(String(40), default="manual")
    last_verified_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), default=None)
