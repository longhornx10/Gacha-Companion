"""Redeem codes and per-player used-state."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from game_companion.db.base import Base, PKMixin, TimestampMixin, UTCDateTime

CODE_STATUS_ACTIVE = "active"
CODE_STATUS_EXPIRED = "expired"
CODE_STATUS_UNKNOWN = "unknown"
CODE_STATUS_RECYCLED = "recycled"  # expired once, reactivated by reliable source


class RedeemCode(PKMixin, TimestampMixin, Base):
    __tablename__ = "redeem_codes"
    __table_args__ = (UniqueConstraint("game_id", "code", name="uq_code"),)

    game_id: Mapped[str] = mapped_column(String(40), index=True)
    code: Mapped[str] = mapped_column(String(80))
    discovered_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=None)
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), default=None)
    status: Mapped[str] = mapped_column(String(20), default=CODE_STATUS_ACTIVE)
    source_id: Mapped[str | None] = mapped_column(
        ForeignKey("research_sources.id", ondelete="SET NULL"), default=None
    )
    notes: Mapped[str | None] = mapped_column(Text, default=None)

    player_states: Mapped[list[PlayerCodeState]] = relationship(
        back_populates="code", cascade="all, delete-orphan", lazy="selectin"
    )


class PlayerCodeState(PKMixin, TimestampMixin, Base):
    __tablename__ = "player_code_states"
    __table_args__ = (UniqueConstraint("code_id", "player_profile_id", name="uq_code_player"),)

    code_id: Mapped[str] = mapped_column(ForeignKey("redeem_codes.id", ondelete="CASCADE"), index=True)
    player_profile_id: Mapped[str] = mapped_column(
        ForeignKey("player_profiles.id", ondelete="CASCADE"), index=True
    )
    used: Mapped[bool] = mapped_column(Boolean, default=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)

    code: Mapped[RedeemCode] = relationship(back_populates="player_states")
