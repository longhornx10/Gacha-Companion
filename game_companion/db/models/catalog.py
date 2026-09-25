"""Game catalog: standard entities fetched from online sources (M25).

Catalog rows are *reference* data — everything that is identical for every
player (agents, W-Engines, light cones, gear sets, their rarity/categories).
Player-owned state (levels, refinements, equipped-by) stays in the roster,
equipment and gear tables; the catalog only supplies the pick-lists and base
metadata. ``source`` keeps provenance honest.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from game_companion.db.base import Base, PKMixin, TimestampMixin, UTCDateTime

CATALOG_CHARACTER = "character"
CATALOG_EQUIPMENT = "equipment"
CATALOG_GEAR_SET = "gear_set"


class CatalogEntry(PKMixin, TimestampMixin, Base):
    __tablename__ = "game_catalog"
    __table_args__ = (
        UniqueConstraint("game_id", "entity_type", "key", name="uq_catalog_entity"),
    )

    game_id: Mapped[str] = mapped_column(String(40), index=True)
    entity_type: Mapped[str] = mapped_column(String(40), index=True)
    key: Mapped[str] = mapped_column(String(120))
    display_name: Mapped[str] = mapped_column(String(200))
    rarity: Mapped[int | None] = mapped_column(Integer, default=None)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    source: Mapped[str | None] = mapped_column(String(60), default=None)
    fetched_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), default=None)


class SourceRun(PKMixin, TimestampMixin, Base):
    """Last outcome of one fetchable source (catalog import or codes refresh).

    One row per (game_id, source_key): re-running a source replaces its row,
    so the UI can always say when a source last succeeded and why it failed.
    """

    __tablename__ = "source_runs"
    __table_args__ = (UniqueConstraint("game_id", "source_key", name="uq_source_run"),)

    game_id: Mapped[str] = mapped_column(String(40), index=True)
    source_key: Mapped[str] = mapped_column(String(80))
    kind: Mapped[str] = mapped_column(String(20))  # catalog | codes
    status: Mapped[str] = mapped_column(String(20))  # ok | error
    detail: Mapped[str | None] = mapped_column(Text, default=None)
    items: Mapped[int] = mapped_column(Integer, default=0)
    fetched_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), default=None)
