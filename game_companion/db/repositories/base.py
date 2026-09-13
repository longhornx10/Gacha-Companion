"""Small generic repository helpers."""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from game_companion.db.base import Base
from game_companion.errors import NotFoundError

M = TypeVar("M", bound=Base)


class BaseRepository(Generic[M]):
    model: type[M]

    def __init__(self, session: Session) -> None:
        self.session = session

    # -- generic helpers -----------------------------------------------------

    def get(self, obj_id: str) -> M | None:
        return self.session.get(self.model, obj_id)

    def get_or_raise(self, obj_id: str, label: str) -> M:
        obj = self.get(obj_id)
        if obj is None:
            raise NotFoundError(f"{label} '{obj_id}' not found")
        return obj

    def add(self, obj: M) -> M:
        self.session.add(obj)
        self.session.flush()
        return obj

    def delete(self, obj: M) -> None:
        self.session.delete(obj)
        self.session.flush()

    def list_all(self, **filters: Any) -> list[M]:
        stmt = select(self.model)
        for attr, value in filters.items():
            stmt = stmt.where(getattr(self.model, attr) == value)
        return list(self.session.scalars(stmt))

    def count(self, **filters: Any) -> int:
        return len(self.list_all(**filters))
