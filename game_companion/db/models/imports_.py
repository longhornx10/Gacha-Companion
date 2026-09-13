"""Screenshot imports: candidate -> validate -> diff -> confirm -> apply."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from game_companion.db.base import Base, PKMixin, TimestampMixin, UTCDateTime

IMPORT_PENDING = "pending"
IMPORT_APPLIED = "applied"
IMPORT_REJECTED = "rejected"
IMPORT_FAILED = "failed"


class ScreenshotImport(PKMixin, TimestampMixin, Base):
    __tablename__ = "screenshot_imports"

    game_id: Mapped[str] = mapped_column(String(40), index=True)
    player_profile_id: Mapped[str] = mapped_column(
        ForeignKey("player_profiles.id", ondelete="CASCADE"), index=True
    )
    screen_type: Mapped[str] = mapped_column(String(60))  # adapter screenshot spec key
    screenshot_name: Mapped[str | None] = mapped_column(String(255), default=None)
    screenshot_hash: Mapped[str | None] = mapped_column(String(64), default=None)
    status: Mapped[str] = mapped_column(String(20), default=IMPORT_PENDING, index=True)
    # Validated candidate payload (adapter schema), never applied on its own.
    candidate: Mapped[dict] = mapped_column(JSON, default=dict)
    diff: Mapped[dict | None] = mapped_column(JSON, default=None)
    confidence: Mapped[float | None] = mapped_column(Float, default=None)
    extracted_fields: Mapped[list] = mapped_column(JSON, default=list)
    rejected_fields: Mapped[list] = mapped_column(JSON, default=list)
    applied_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), default=None)
    error: Mapped[str | None] = mapped_column(Text, default=None)
