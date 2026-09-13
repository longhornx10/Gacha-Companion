"""Resources (inventory counters) and planned per-character demand for thresholds."""

from __future__ import annotations

from sqlalchemy import JSON, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from game_companion.db.base import Base, PKMixin, TimestampMixin


class Resource(PKMixin, TimestampMixin, Base):
    __tablename__ = "resources"
    __table_args__ = (
        UniqueConstraint("game_id", "player_profile_id", "resource_key", name="uq_resource_key"),
    )

    game_id: Mapped[str] = mapped_column(String(40), index=True)
    player_profile_id: Mapped[str] = mapped_column(
        ForeignKey("player_profiles.id", ondelete="CASCADE"), index=True
    )
    resource_key: Mapped[str] = mapped_column(String(80))
    quantity: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    data: Mapped[dict] = mapped_column(JSON, default=dict)


class ResourcePlanEntry(PKMixin, TimestampMixin, Base):
    """Planned requirement of ``amount`` of a resource for one character.

    Together with the adapter's single-character max target (X) these entries
    form the planned demand (Y) used by deterministic threshold evaluation.
    """

    __tablename__ = "resource_plan_entries"

    game_id: Mapped[str] = mapped_column(String(40), index=True)
    player_profile_id: Mapped[str] = mapped_column(
        ForeignKey("player_profiles.id", ondelete="CASCADE"), index=True
    )
    resource_key: Mapped[str] = mapped_column(String(80), index=True)
    character_id: Mapped[str | None] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), index=True, default=None
    )
    amount: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str | None] = mapped_column(Text, default=None)
