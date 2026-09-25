"""Catalog service (M25): fetch online sources into the reference catalog.

The catalog holds what is identical for every player (agents, equipment,
gear sets — names, rarity, categories). Player state stays in roster/equipment/
gear tables. Every source run is recorded in ``source_runs`` — success and
failure alike — so the UI can say exactly when data was last refreshed and
why a source is unavailable. A failing source never blocks the others.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from game_companion.core.games.base import GameAdapter
from game_companion.db.models import CatalogEntry, SourceRun
from game_companion.errors import NotFoundError, ValidationError

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


def fetch_payload(spec: dict, transport: httpx.BaseTransport | None) -> Any:
    """Fetch one source spec ({url, kind}). Returns parsed JSON or raw text."""
    with httpx.Client(transport=transport, timeout=60, follow_redirects=True) as client:
        response = client.get(spec["url"], headers={"User-Agent": BROWSER_UA})
        response.raise_for_status()
        if spec.get("kind", "json") == "json":
            return response.json()
        return response.text


def record_run(
    session: Session,
    game_id: str,
    source_key: str,
    kind: str,
    status: str,
    *,
    detail: str | None = None,
    items: int = 0,
) -> SourceRun:
    """Upsert the single per-source run row (keeps the latest outcome only)."""
    row = session.scalars(
        select(SourceRun).where(
            SourceRun.game_id == game_id, SourceRun.source_key == source_key
        )
    ).first()
    if row is None:
        row = SourceRun(game_id=game_id, source_key=source_key, kind=kind)
        session.add(row)
    row.status = status
    row.detail = detail
    row.items = items
    row.fetched_at = datetime.now(UTC)
    session.flush()
    return row


class CatalogService:
    def __init__(self, session: Session, adapter: GameAdapter) -> None:
        self.session = session
        self.adapter = adapter

    # -- queries ---------------------------------------------------------------

    def entries(self, entity_type: str | None = None) -> list[CatalogEntry]:
        stmt = select(CatalogEntry).where(CatalogEntry.game_id == self.adapter.game_id)
        if entity_type:
            stmt = stmt.where(CatalogEntry.entity_type == entity_type)
        stmt = stmt.order_by(CatalogEntry.display_name)
        return list(self.session.scalars(stmt))

    def find(self, entity_type: str, key: str) -> CatalogEntry | None:
        return self.session.scalars(
            select(CatalogEntry).where(
                CatalogEntry.game_id == self.adapter.game_id,
                CatalogEntry.entity_type == entity_type,
                CatalogEntry.key == key,
            )
        ).first()

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for entry in self.entries():
            out[entry.entity_type] = out.get(entry.entity_type, 0) + 1
        return out

    def runs(self) -> list[SourceRun]:
        stmt = (
            select(SourceRun)
            .where(SourceRun.game_id == self.adapter.game_id)
            .order_by(SourceRun.source_key)
        )
        return list(self.session.scalars(stmt))

    def run_for(self, source_key: str) -> SourceRun | None:
        return self.session.scalars(
            select(SourceRun).where(
                SourceRun.game_id == self.adapter.game_id,
                SourceRun.source_key == source_key,
            )
        ).first()

    # -- refresh ---------------------------------------------------------------

    def refresh(
        self,
        source_key: str = "auto",
        *,
        transport: httpx.BaseTransport | None = None,
        skip_entities: set[str] | None = None,
    ) -> dict[str, Any]:
        """Fetch one source (or all with ``auto``) and upsert its catalog rows.

        Returns {source_key: {status, detail?, items, added, updated}}. A bad
        source is recorded honestly and does not stop the others.
        ``skip_entities`` omits whole entity families from an ``auto`` run
        (the scheduler refreshes banners on their own, shorter, cadence).
        """
        sources = self.adapter.catalog_sources()
        if not sources:
            raise ValidationError(
                f"game '{self.adapter.game_id}' declares no catalog sources"
            )
        keys = sorted(sources) if source_key == "auto" else [source_key]
        if skip_entities:
            keys = [
                k for k in keys
                if sources[k].get("entity", "character") not in skip_entities
            ]
        if source_key != "auto" and source_key not in sources:
            raise NotFoundError(
                f"unknown catalog source '{source_key}' (known: {sorted(sources)})"
            )
        self._prune_removed_sources(set(sources))

        now = datetime.now(UTC)
        summary: dict[str, Any] = {}
        for key in keys:
            spec = sources[key]
            try:
                payload = fetch_payload(spec, transport)
                rows = self.adapter.catalog_transform(key, payload)
                if not rows:
                    raise ValueError("source returned no parseable rows")
            except Exception as exc:  # noqa: BLE001 — every failure is recorded, none fatal
                record_run(
                    self.session, self.adapter.game_id, key, "catalog",
                    "error", detail=f"{type(exc).__name__}: {exc}",
                )
                summary[key] = {"status": "error", "detail": str(exc), "items": 0}
                continue
            added, updated = self._upsert_rows(spec.get("entity", "character"), rows, now)
            record_run(
                self.session, self.adapter.game_id, key, "catalog",
                "ok", items=len(rows),
            )
            summary[key] = {
                "status": "ok", "items": len(rows), "added": added, "updated": updated,
            }
        return summary

    def _prune_removed_sources(self, declared: set[str]) -> None:
        """Drop run rows for catalog sources the adapter no longer declares."""
        for run in self.runs():
            if run.kind == "catalog" and run.source_key not in declared:
                self.session.delete(run)
        self.session.flush()

    def _upsert_rows(
        self, entity_type: str, rows: list[dict[str, Any]], fetched_at: datetime
    ) -> tuple[int, int]:
        added = updated = 0
        for row in rows:
            key = str(row.get("key") or "").strip()
            name = str(row.get("name") or "").strip()
            if not key or not name:
                continue
            entry = self.find(entity_type, key)
            if entry is None:
                entry = CatalogEntry(
                    game_id=self.adapter.game_id, entity_type=entity_type, key=key
                )
                self.session.add(entry)
                added += 1
            else:
                updated += 1
            entry.display_name = name
            entry.rarity = row.get("rarity")
            entry.meta = row.get("meta") or {}
            entry.source = row.get("source")
            entry.fetched_at = fetched_at
        self.session.flush()
        return added, updated
