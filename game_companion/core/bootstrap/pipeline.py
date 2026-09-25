"""Bootstrap pipeline (M24): fetch a source, transform, stage for review.

Fetch -> transform -> stage as pending change records (never silent
overwrites). With ``apply=True`` the transformed rows are additionally written
to ``<data_dir>/bootstrap/<game>/<entity>.json`` with full provenance
(``_meta``: source URL, fetch time, review status). Data honesty extends to
sourcing: every datum knows where it came from.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import httpx

from game_companion.config import Settings
from game_companion.core.games.base import GameAdapter
from game_companion.db.models import ChangeRecord
from game_companion.db.models.research import CHANGE_PENDING
from game_companion.db.repositories import ResearchRepository
from game_companion.errors import NotFoundError, ValidationError


class BootstrapService:
    def __init__(self, session, adapter: GameAdapter, settings: Settings) -> None:
        self.session = session
        self.adapter = adapter
        self.settings = settings
        self.changes = ResearchRepository(session)

    def run(self, source_key: str, *, transport: httpx.BaseTransport | None = None, apply: bool = False) -> dict:
        sources = self.adapter.bootstrap_sources()
        if not sources:
            raise ValidationError(f"game '{self.adapter.game_id}' declares no bootstrap sources")
        if source_key == "auto":
            source_key = sorted(sources)[0]
        spec = sources.get(source_key)
        if spec is None:
            raise NotFoundError(
                f"unknown bootstrap source '{source_key}' (known: {sorted(sources)})"
            )

        fetched_at = datetime.now(UTC)
        with httpx.Client(transport=transport, timeout=60, follow_redirects=True) as client:
            response = client.get(spec["url"])
            response.raise_for_status()
            payload = response.json() if spec.get("kind", "json") == "json" else response.text

        rows = self.adapter.bootstrap_transform(source_key, payload)
        if not rows:
            return {"source": source_key, "staged": 0, "applied": False,
                    "note": "transform produced no rows — nothing staged"}

        evidence = [
            {"url": spec["url"], "source": source_key, "retrieved_at": fetched_at.isoformat()}
        ]
        staged = 0
        for row in rows:
            key = str(row.get("key") or "")
            if not key:
                continue
            existing = self.adapter.character_meta(key)
            record = ChangeRecord(
                game_id=self.adapter.game_id,
                entity_type=spec.get("entity", "character_meta"),
                entity_key=key,
                detected_at=fetched_at,
                previous_value=existing,
                proposed_value=row,
                evidence=evidence,
                review_status=CHANGE_PENDING,
                notes=f"bootstrap via {source_key}",
            )
            self.session.add(record)
            staged += 1
        self.session.flush()

        applied_path = None
        if apply:
            applied_path = self._write_rows(source_key, spec, rows, fetched_at)

        return {
            "source": source_key,
            "staged": staged,
            "applied": apply,
            "applied_path": str(applied_path) if applied_path else None,
            "review": "pending — approve via /api/games/{game}/changes, then run --apply next time",
            "provenance": {"url": spec["url"], "fetched_at": fetched_at.isoformat()},
        }

    def _write_rows(self, source_key: str, spec: dict, rows: list[dict[str, Any]], fetched_at) -> Any:
        target = (
            self.settings.resolved_data_dir
            / "bootstrap"
            / self.adapter.game_id
            / f"{spec.get('entity', 'character_meta')}.json"
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        document = {
            "_meta": {
                "source": spec["url"],
                "source_key": source_key,
                "fetched_at": fetched_at.isoformat(),
                "review": "machine_staged",
            },
            "rows": rows,
        }
        target.write_text(json.dumps(document, indent=2, ensure_ascii=False), encoding="utf-8")
        return target
