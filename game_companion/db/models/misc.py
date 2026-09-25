"""Encounters (endgame modes/slots), stored recommendations, audit results."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from game_companion.db.base import Base, PKMixin, TimestampMixin, UTCDateTime


class Encounter(PKMixin, TimestampMixin, Base):
    __tablename__ = "encounters"
    __table_args__ = (UniqueConstraint("game_id", "key", name="uq_encounter_key"),)

    game_id: Mapped[str] = mapped_column(String(40), index=True)
    key: Mapped[str] = mapped_column(String(80))
    name: Mapped[str] = mapped_column(String(160))
    mode: Mapped[str] = mapped_column(String(60), default="endgame")
    data: Mapped[dict] = mapped_column(JSON, default=dict)

    slots: Mapped[list[EncounterSlot]] = relationship(
        back_populates="encounter", cascade="all, delete-orphan", lazy="selectin",
        order_by="EncounterSlot.slot_index",
    )


class EncounterSlot(PKMixin, Base):
    __tablename__ = "encounter_slots"
    __table_args__ = (UniqueConstraint("encounter_id", "slot_index", name="uq_encounter_slot"),)

    encounter_id: Mapped[str] = mapped_column(
        ForeignKey("encounters.id", ondelete="CASCADE"), index=True
    )
    slot_index: Mapped[int] = mapped_column(Integer)
    constraints: Mapped[dict] = mapped_column(JSON, default=dict)

    encounter: Mapped[Encounter] = relationship(back_populates="slots")


class Recommendation(PKMixin, TimestampMixin, Base):
    __tablename__ = "recommendations"

    game_id: Mapped[str] = mapped_column(String(40), index=True)
    player_profile_id: Mapped[str] = mapped_column(
        ForeignKey("player_profiles.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(60))  # team|gear|upgrade|audit|allocation
    subject: Mapped[str] = mapped_column(String(120))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    basis: Mapped[dict] = mapped_column(JSON, default=dict)


class AuditResult(PKMixin, TimestampMixin, Base):
    __tablename__ = "audit_results"

    game_id: Mapped[str] = mapped_column(String(40), index=True)
    player_profile_id: Mapped[str] = mapped_column(
        ForeignKey("player_profiles.id", ondelete="CASCADE"), index=True
    )
    character_id: Mapped[str | None] = mapped_column(
        ForeignKey("characters.id", ondelete="SET NULL"), default=None
    )
    status: Mapped[str] = mapped_column(String(40), default="ok")
    issues: Mapped[list] = mapped_column(JSON, default=list)
    checked_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=None)


class Achievement(PKMixin, TimestampMixin, Base):
    __tablename__ = "achievements"
    __table_args__ = (
        UniqueConstraint("player_profile_id", "game_id", "key", name="uq_achievement"),
    )

    player_profile_id: Mapped[str] = mapped_column(
        ForeignKey("player_profiles.id", ondelete="CASCADE"), index=True
    )
    game_id: Mapped[str] = mapped_column(String(40), index=True)
    key: Mapped[str] = mapped_column(String(60))
    unlocked_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), default=None, nullable=True)
