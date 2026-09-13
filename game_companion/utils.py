"""Small shared utilities: IDs and UTC time handling."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime


def new_id() -> str:
    """Compact random UUID (32 hex chars) used as primary key."""
    return uuid.uuid4().hex


def utcnow() -> datetime:
    """Timezone-aware UTC now. Stored naive-UTC in SQLite via UTCDateTime."""
    return datetime.now(UTC)


def ensure_utc(dt: datetime) -> datetime:
    """Return a timezone-aware UTC datetime (naive input is assumed UTC)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def to_iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return ensure_utc(dt).isoformat().replace("+00:00", "Z")
