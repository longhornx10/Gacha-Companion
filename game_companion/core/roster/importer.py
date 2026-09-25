"""Deterministic roster importer (M21).

Parses a plain-text roster (the "PHOENIX ROSTER ZZZ.txt" shape) or our own
JSON into character entries, diffs them against the authoritative roster, and
stages the result as a reviewable import (same confirm/reject flow as
screenshots). Unparseable lines are REPORTED, never guessed — data honesty
applies to text just as much as to screenshots.
"""

from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy.orm import Session

from game_companion.core.games.base import GameAdapter
from game_companion.core.roster.service import RosterService
from game_companion.db.models import ScreenshotImport
from game_companion.db.repositories import CharacterRepository, ImportRepository
from game_companion.errors import ValidationError

SCREEN_TYPE = "roster_txt"

_LEVEL_RE = re.compile(r"(?i)\b(?:lv|lvl|level)\.?\s*([0-9]{1,3})\b")
_DUPE_RE = re.compile(r"\b[Mm]\s*([0-6])\b")
_ENGINE_RE = re.compile(r"(?i)\bw-?engine\s*[:\-]?\s*(.+?)\s*$")


def parse_roster_text(text: str, adapter: GameAdapter) -> dict:
    """Parse roster text into entries. Returns {entries, unresolved, header}."""
    entries: list[dict] = []
    unresolved: list[dict] = []
    header: str | None = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if _looks_like_header(line, entries, adapter):
            header = line
            continue

        level = _LEVEL_RE.search(line)
        dupe = _DUPE_RE.search(line)
        engine = _ENGINE_RE.search(line)

        name_part = line
        for match in (level, dupe, engine):
            if match:
                name_part = name_part.replace(match.group(0), " ")
        name = re.sub(r"[,;\t]+", " ", name_part)
        name = re.sub(r"\s+", " ", name).strip(" -–—:.")
        if not name:
            unresolved.append({"line": raw_line.strip(), "reason": "no readable name"})
            continue

        key = adapter.resolve_character_key(name)
        if key is None:
            unresolved.append({"line": raw_line.strip(), "reason": f"name '{name}' not in game data"})
            continue

        meta = adapter.character_meta(key) or {}
        entries.append(
            {
                "key": key,
                "display_name": meta.get("name") or name,
                "level": int(level.group(1)) if level else None,
                "duplication_level": int(dupe.group(1)) if dupe else None,
                "engine_name": engine.group(1).strip() if engine else None,
                "line": raw_line.strip(),
            }
        )
    return {"entries": entries, "unresolved": unresolved, "header": header}


def _looks_like_header(line: str, entries: list, adapter: GameAdapter) -> bool:
    """First line with no digits and no resolvable name is treated as a title."""
    if entries:
        return False
    if any(char.isdigit() for char in line):
        return False
    return adapter.resolve_character_key(line) is None


def parse_roster_json(payload: dict, adapter: GameAdapter) -> dict:
    """Parse our own JSON shape: [{key|name, level?, duplication_level?}...]."""
    entries: list[dict] = []
    unresolved: list[dict] = []
    rows = payload.get("characters") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise ValidationError("roster JSON must be a list or {\"characters\": [...]}")
    for row in rows:
        if not isinstance(row, dict):
            unresolved.append({"line": json.dumps(row), "reason": "not an object"})
            continue
        key = row.get("key") or adapter.resolve_character_key(str(row.get("name", "")))
        if not key:
            unresolved.append({"line": json.dumps(row), "reason": "no key and name unresolved"})
            continue
        entries.append(
            {
                "key": key,
                "display_name": row.get("name")
                or (adapter.character_meta(key) or {}).get("name", key),
                "level": row.get("level"),
                "duplication_level": row.get("duplication_level"),
                "engine_name": row.get("engine"),
                "line": json.dumps(row),
            }
        )
    return {"entries": entries, "unresolved": unresolved, "header": None}


def diff_entries(session: Session, adapter: GameAdapter, game_id: str, player_id: str, parsed: dict) -> dict:
    changes: list[dict] = []
    for entry in parsed["entries"]:
        existing = CharacterRepository(session).find_by_key(game_id, player_id, entry["key"])
        if existing is None:
            changes.append(
                {
                    "action": "create",
                    "entity": "character",
                    "key": entry["key"],
                    "proposed": {
                        "level": entry["level"],
                        "duplication_level": entry["duplication_level"],
                    },
                }
            )
            continue
        for field in ("level", "duplication_level"):
            if entry[field] is not None and getattr(existing, field) != entry[field]:
                changes.append(
                    {
                        "action": "update",
                        "entity": "character",
                        "key": entry["key"],
                        "field": field,
                        "current": getattr(existing, field),
                        "proposed": entry[field],
                    }
                )
    return {"changes": changes, "unresolved": parsed["unresolved"], "header": parsed["header"]}


def stage_roster_import(session: Session, adapter: GameAdapter, game_id: str, player_id: str, parsed: dict) -> ScreenshotImport:
    if not parsed["entries"] and not parsed["unresolved"]:
        raise ValidationError("nothing to import: the text had no usable lines")
    diff = diff_entries(session, adapter, game_id, player_id, parsed)
    row = ImportRepository(session).add(
        ScreenshotImport(
            game_id=game_id,
            player_profile_id=player_id,
            screen_type=SCREEN_TYPE,
            screenshot_name=parsed.get("header"),
            status="pending",
            candidate={"entries": parsed["entries"]},
            diff=diff,
            extracted_fields=[e["key"] for e in parsed["entries"]],
            rejected_fields=[u["reason"] for u in parsed["unresolved"]],
        )
    )
    session.flush()
    return row


def apply_roster_entries(
    session: Session, adapter: GameAdapter, game_id: str, player_id: str, entries: list[dict[str, Any]]
) -> list[str]:
    """Confirm path: apply parsed entries. Only resolvable entries reach here."""
    roster = RosterService(session, adapter)
    applied: list[str] = []
    for entry in entries:
        character = CharacterRepository(session).find_by_key(game_id, player_id, entry["key"])
        if character is None:
            character = roster.create_character(
                game_id,
                player_id,
                {"key": entry["key"], "display_name": entry.get("display_name") or entry["key"]},
            )
        patch: dict[str, Any] = {"verified": True, "source": "roster_import"}
        if entry.get("level") is not None:
            patch["level"] = entry["level"]
        if entry.get("duplication_level") is not None:
            patch["duplication_level"] = entry["duplication_level"]
        roster.update_character(character, patch)
        applied.append(f"{entry['key']} saved (level {entry.get('level')}, {adapter.terminology().duplication} {entry.get('duplication_level')})")
    return applied


def summarize(row: ScreenshotImport) -> dict:
    diff = row.diff or {}
    return {
        "import_id": row.id,
        "status": row.status,
        "entries": len((row.candidate or {}).get("entries", [])),
        "changes": len(diff.get("changes", [])),
        "unresolved": diff.get("unresolved", []),
        "changes_detail": diff.get("changes", []),
        "note": "review the changes, then confirm or discard",
    }
