"""Combat history and the personal training model."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from game_companion.db.base import Base, PKMixin, TimestampMixin, UTCDateTime


class CombatResult(PKMixin, TimestampMixin, Base):
    """One recorded encounter attempt. Historical rows are never mutated when
    builds change — team/build state is snapshotted at record time."""

    __tablename__ = "combat_results"

    game_id: Mapped[str] = mapped_column(String(40), index=True)
    player_profile_id: Mapped[str] = mapped_column(
        ForeignKey("player_profiles.id", ondelete="CASCADE"), index=True
    )
    encounter_key: Mapped[str] = mapped_column(String(80), index=True)
    encounter_slot: Mapped[str | None] = mapped_column(String(40), default=None)
    played_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=None)
    team_id: Mapped[str | None] = mapped_column(
        ForeignKey("teams.id", ondelete="SET NULL"), default=None
    )
    # {"members": [{"key","display_name","level","duplication_level"}...], "name": ...}
    team_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    build_snapshot: Mapped[dict | None] = mapped_column(JSON, default=None)
    score: Mapped[float | None] = mapped_column(Float, default=None)
    rank: Mapped[str | None] = mapped_column(String(40), default=None)
    stars: Mapped[int | None] = mapped_column(Integer, default=None)
    cleared: Mapped[bool | None] = mapped_column(Boolean, default=None)
    clear_time_seconds: Mapped[float | None] = mapped_column(Float, default=None)
    retries: Mapped[int | None] = mapped_column(Integer, default=None)
    difficulty: Mapped[str | None] = mapped_column(String(40), default=None)
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    data: Mapped[dict] = mapped_column(JSON, default=dict)


class TrainingIssue(PKMixin, TimestampMixin, Base):
    __tablename__ = "training_issues"

    game_id: Mapped[str] = mapped_column(String(40), index=True)
    player_profile_id: Mapped[str] = mapped_column(
        ForeignKey("player_profiles.id", ondelete="CASCADE"), index=True
    )
    category: Mapped[str] = mapped_column(String(60))
    description: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(20), default="medium")
    status: Mapped[str] = mapped_column(String(20), default="open")  # open|watch|resolved
    character_keys: Mapped[list] = mapped_column(JSON, default=list)
    first_seen_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=None)
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=None)
    occurrences: Mapped[int] = mapped_column(Integer, default=1)
    notes: Mapped[str | None] = mapped_column(Text, default=None)


class TrainingGoal(PKMixin, TimestampMixin, Base):
    __tablename__ = "training_goals"

    game_id: Mapped[str] = mapped_column(String(40), index=True)
    player_profile_id: Mapped[str] = mapped_column(
        ForeignKey("player_profiles.id", ondelete="CASCADE"), index=True
    )
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="active")  # active|done|dropped
    target: Mapped[dict | None] = mapped_column(JSON, default=None)
    progress_notes: Mapped[str | None] = mapped_column(Text, default=None)
