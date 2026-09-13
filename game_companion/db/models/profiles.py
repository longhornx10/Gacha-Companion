"""Player profiles and preferences (global + per-game scope)."""

from __future__ import annotations

from sqlalchemy import JSON, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from game_companion.db.base import Base, PKMixin, TimestampMixin

SCOPE_GLOBAL = "global"


class PlayerProfile(PKMixin, TimestampMixin, Base):
    __tablename__ = "player_profiles"

    display_name: Mapped[str] = mapped_column(String(120))
    notes: Mapped[str | None] = mapped_column(Text, default=None)


class PlayerPreference(PKMixin, TimestampMixin, Base):
    __tablename__ = "player_preferences"
    __table_args__ = (
        UniqueConstraint("player_profile_id", "scope", "key", name="uq_player_pref_scope_key"),
    )

    player_profile_id: Mapped[str] = mapped_column(
        ForeignKey("player_profiles.id", ondelete="CASCADE"), index=True
    )
    scope: Mapped[str] = mapped_column(String(40), default=SCOPE_GLOBAL)
    key: Mapped[str] = mapped_column(String(80))
    value: Mapped[dict | list | str | int | float | bool | None] = mapped_column(JSON, default=None)
