"""Declarative base, PK/timestamp mixins, and a UTC-safe DateTime type.

Convention: all datetimes are UTC. SQLite stores naive UTC; ``UTCDateTime``
attaches/normalizes tzinfo so application code always sees aware UTC datetimes.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, String, types
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from game_companion.utils import new_id, utcnow


class Base(DeclarativeBase):
    pass


class UTCDateTime(types.TypeDecorator):
    """DateTime stored as naive UTC, returned timezone-aware UTC."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: object) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is not None:
            return value.astimezone(UTC).replace(tzinfo=None)
        return value

    def process_result_value(self, value: datetime | None, dialect: object) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC)


class PKMixin:
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow, nullable=False)
