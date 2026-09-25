"""Screenshot ingestion (Milestone 5).

Workflow: screenshot -> VLM extraction (or manual candidate) -> schema
validation -> diff vs current state -> explicit user confirmation ->
transactional apply. Raw VLM output never writes to the DB directly.
"""

from __future__ import annotations

import base64
import hashlib
from typing import Any

from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.orm import Session

from game_companion.core.games.base import GameAdapter
from game_companion.core.roster.service import RosterService
from game_companion.db.models import ScreenshotImport
from game_companion.db.repositories import ImportRepository, ResourceRepository
from game_companion.errors import LLMError, NotFoundError, ValidationError
from game_companion.utils import utcnow


def validate_candidate(adapter: GameAdapter, screen_type: str, candidate: dict) -> dict:
    specs = adapter.screenshot_specs()
    spec = specs.get(screen_type)
    if spec is None:
        raise ValidationError(
            f"unknown screen_type '{screen_type}' for '{adapter.game_id}' "
            f"(known: {sorted(specs)})"
        )
    try:
        validated = spec.schema.model_validate(candidate)
    except PydanticValidationError as exc:
        raise ValidationError(f"candidate failed {screen_type} schema validation: {exc}") from exc
    return validated.model_dump(exclude_none=True)


# Candidate keys that map straight onto character columns (generic vocabulary;
# adapters' prompts map game-specific screen labels onto these keys).
_CHARACTER_FIELDS = ("level", "duplication_level")


def diff_candidate(
    session: Session, adapter: GameAdapter, game_id: str, player_id: str,
    screen_type: str, candidate: dict, character_hint: str | None,
) -> dict:
    """Human-readable proposed changes vs authoritative state (no writes)."""
    changes: list[dict] = []
    character = _resolve_character(session, adapter, game_id, player_id, screen_type, candidate, character_hint)
    if screen_type == "character_overview":
        if character is None:
            changes.append({"action": "requirement", "detail": "character must exist before applying overview data"})
        else:
            for field in _CHARACTER_FIELDS:
                if candidate.get(field) is not None:
                    current = getattr(character, field)
                    if current != candidate[field]:
                        changes.append({
                            "action": "update", "entity": "character", "key": character.key,
                            "field": field, "current": current, "proposed": candidate[field],
                        })
    elif screen_type == "skills" and character is not None:
        valid_keys = {d.key: d.name for d in adapter.skill_definitions()}
        for skill in candidate.get("skills") or []:
            key = skill.get("key")
            name = skill.get("name")
            level = skill.get("level")
            resolved = key or next((k for k, n in valid_keys.items() if name and n.lower() == name.lower()), None)
            if resolved and resolved in valid_keys and level is not None:
                current = next((s.level for s in character.skills if s.skill_key == resolved), None)
                if current != level:
                    changes.append({
                        "action": "update", "entity": "skill", "key": f"{character.key}.{resolved}",
                        "field": "level", "current": current, "proposed": level,
                    })
    elif screen_type == "equipment":
        if candidate.get("equipment_name") is not None:
            changes.append({
                "action": "upsert", "entity": "equipment",
                "key": candidate.get("equipment_key") or _slugify(candidate["equipment_name"]),
                "proposed": {
                    "display_name": candidate["equipment_name"],
                    "level": candidate.get("level"),
                    "refinement": candidate.get("refinement"),
                    "character": character.key if character else character_hint,
                },
            })
    elif screen_type == "gear_detail":
        changes.append({
            "action": "create", "entity": "gear",
            "proposed": {
                "slot": candidate.get("slot"),
                "set_key": candidate.get("set_key"),
                "rarity": candidate.get("rarity"),
                "level": candidate.get("level"),
                "main_stat_key": candidate.get("main_stat_key"),
                "main_stat_value": candidate.get("main_stat_value"),
                "substats": candidate.get("substats") or [],
                "character": character.key if character else character_hint,
            },
        })
    elif screen_type == "gear_list":
        for disc in candidate.get("discs") or []:
            if disc.get("slot"):
                changes.append({
                    "action": "note", "entity": "gear_loadout",
                    "detail": f"slot {disc['slot']}: {disc.get('set_name')} "
                              f"{disc.get('main_stat_key')} (lv {disc.get('level')}) — "
                              "confirm on the disc detail screen before storing",
                })
    elif screen_type == "resources":
        for entry in candidate.get("resources") or []:
            name = entry.get("name") or entry.get("key")
            key = entry.get("key") or (adapter.resolve_character_key(name) if name else None)
            resource_key = entry.get("key") or _slugify(name or "")
            if resource_key and entry.get("quantity") is not None:
                current_row = ResourceRepository(session).find_by_key(game_id, player_id, resource_key)
                changes.append({
                    "action": "upsert", "entity": "resource", "key": resource_key,
                    "field": "quantity", "current": current_row.quantity if current_row else None,
                    "proposed": entry["quantity"],
                })
    return {"changes": changes, "character_key": character.key if character else None}


def _resolve_character(session, adapter, game_id, player_id, screen_type, candidate, hint):
    roster = RosterService(session, adapter)
    for name in (hint, candidate.get("character_key"), candidate.get("character_name")):
        if not name:
            continue
        key = adapter.resolve_character_key(str(name)) or str(name)
        try:
            return roster.resolve_character(game_id, player_id, key.lower())
        except NotFoundError:
            continue
    return None


def _slugify(text: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in text.strip().lower()).strip("_")


class ImportService:
    def __init__(self, session: Session, adapter: GameAdapter) -> None:
        self.session = session
        self.adapter = adapter
        self.imports = ImportRepository(session)

    def create_import(
        self,
        game_id: str,
        player_id: str,
        *,
        screen_type: str,
        candidate: dict | None = None,
        image_base64: str | None = None,
        screenshot_name: str | None = None,
        character_hint: str | None = None,
        llm=None,
    ) -> dict:
        spec = self.adapter.screenshot_specs().get(screen_type)
        if spec is None:
            raise ValidationError(
                f"unknown screen_type '{screen_type}' (known: {sorted(self.adapter.screenshot_specs())})"
            )
        image_hash = None
        error: str | None = None
        validated: dict = {}
        confidence = None
        rejected: list[str] = []

        if candidate is not None:
            validated = validate_candidate(self.adapter, screen_type, candidate)
        elif image_base64:
            if llm is None or not getattr(llm, "configured", False):
                raise NotFoundError("no LLM configured for vision extraction; pass a manual candidate instead")
            if not getattr(llm, "vision_capable", True):
                # heuristic said no: broker "auto" routing may still accept
                # images, so ask the endpoint directly. A clear image refusal
                # stops here; probe errors (network, 5xx) fall through so the
                # real extraction attempt surfaces the honest error instead.
                try:
                    refused = not llm.probe_vision()
                except LLMError:
                    refused = False
                if refused:
                    raise ValidationError(
                        f"the current model '{getattr(llm, 'model', '')}' refused a test image, "
                        "so it cannot read screenshots. Pick a vision model in Settings → "
                        "Assistant model (or set the vision override there) and retry."
                    )
            try:
                raw = base64.b64decode(image_base64)
                image_hash = hashlib.sha256(raw).hexdigest()
                instruction = (
                    f"{spec.prompt}\n\nGame: {self.adapter.display_name}."
                    + (f"\nThe player says this screen is about: {character_hint}." if character_hint else "")
                )
                result = llm.extract_structured(spec.schema, instruction, images=[raw])
                validated = result.model_dump(exclude_none=True)
            except (LLMError, PydanticValidationError, ValueError) as exc:
                error = f"extraction failed: {exc}"
        else:
            raise ValidationError("provide image_base64 or a manual candidate dict")

        if validated:
            confidence = validated.pop("extraction_confidence", None)
            extracted = sorted(k for k, v in validated.items() if v is not None and v != [])
            proposed_nulls = sorted(k for k, v in validated.items() if v is None or v == [])
            rejected = proposed_nulls

        diff = (
            diff_candidate(self.session, self.adapter, game_id, player_id, screen_type, validated, character_hint)
            if validated and not error
            else None
        )
        row = self.imports.add(
            ScreenshotImport(
                game_id=game_id,
                player_profile_id=player_id,
                screen_type=screen_type,
                screenshot_name=screenshot_name,
                screenshot_hash=image_hash,
                status="failed" if error else "pending",
                candidate=validated,
                diff=diff,
                confidence=confidence,
                extracted_fields=extracted if validated else [],
                rejected_fields=rejected,
                error=error,
            )
        )
        return {
            "import_id": row.id,
            "status": row.status,
            "candidate": row.candidate,
            "diff": row.diff,
            "confidence": row.confidence,
            "extracted_fields": row.extracted_fields,
            "rejected_fields": row.rejected_fields,
            "error": row.error,
        }

    def confirm(self, import_id: str) -> dict:
        """Apply the validated candidate to the DB inside one transaction."""
        row = self.imports.get_or_raise(import_id, "import")
        if row.status != "pending":
            raise ValidationError(f"import is '{row.status}', only pending imports can be confirmed")
        if not row.candidate:
            raise ValidationError("import has no candidate to apply")
        hint = (row.diff or {}).get("character_key") if row.diff else None
        if row.screen_type == "roster_txt":
            from game_companion.core.roster.importer import apply_roster_entries

            applied = apply_roster_entries(
                self.session, self.adapter, row.game_id, row.player_profile_id,
                row.candidate.get("entries", []),
            )
        else:
            applied = _apply_candidate(
                self.session, self.adapter, row.game_id, row.player_profile_id,
                row.screen_type, row.candidate, character_hint=hint,
            )
        row.status = "applied"
        row.applied_at = utcnow()
        self.session.flush()
        return {"import_id": row.id, "status": row.status, "applied": applied}

    def reject(self, import_id: str) -> dict:
        row = self.imports.get_or_raise(import_id, "import")
        if row.status != "pending":
            raise ValidationError(f"import is '{row.status}', only pending imports can be rejected")
        row.status = "rejected"
        self.session.flush()
        return {"import_id": row.id, "status": row.status}


# --------------------------------------------------------------------------- #
# Apply logic (the ONLY path from candidates into the database)
# --------------------------------------------------------------------------- #

def _apply_candidate(
    session: Session, adapter: GameAdapter, game_id: str, player_id: str,
    screen_type: str, candidate: dict, character_hint: str | None = None,
) -> list[str]:
    applied: list[str] = []
    roster = RosterService(session, adapter)
    character = _resolve_character(
        session, adapter, game_id, player_id, screen_type, candidate, character_hint
    )

    if screen_type == "character_overview":
        if character is None:
            raise ValidationError("cannot apply: character does not exist yet (create it first)")
        payload: dict[str, Any] = {"verified": True, "source": "screenshot_import"}
        for field in _CHARACTER_FIELDS:
            if candidate.get(field) is not None:
                payload[field] = candidate[field]
        data_patch = {
            k: candidate[k]
            for k in ("attribute", "specialty", "faction")
            if candidate.get(k)
        }
        if data_patch:
            payload["data"] = data_patch
        roster.update_character(character, payload)
        applied.append(f"character {character.key} updated from screenshot (verified)")

    elif screen_type == "skills":
        if character is None:
            raise ValidationError("cannot apply: character does not exist yet (create it first)")
        valid_keys = {d.key: d.name for d in adapter.skill_definitions()}
        skills: dict[str, int | None] = {}
        for skill in candidate.get("skills") or []:
            key = skill.get("key") or next(
                (k for k, n in valid_keys.items() if skill.get("name") and n.lower() == skill["name"].lower()),
                None,
            )
            if key in valid_keys and skill.get("level") is not None:
                skills[key] = skill["level"]
        if skills:
            roster.set_skills(character, skills)
            character.last_verified_at = utcnow()
            applied.append(f"skills updated for {character.key}: {skills}")
        else:
            raise ValidationError("no readable skill levels to apply")

    elif screen_type == "equipment":
        from game_companion.core.equipment.service import EquipmentService

        name = candidate.get("equipment_name")
        if not name:
            raise ValidationError("no equipment name readable; refusing to create a blank record")
        equipment = EquipmentService(session, adapter)
        item = equipment.create(
            game_id,
            player_id,
            {
                "key": candidate.get("equipment_key") or _slugify(name),
                "display_name": name,
                "level": candidate.get("level"),
                "refinement": candidate.get("refinement"),
                "character": character.key if character else None,
                "verified": True,
                "source": "screenshot_import",
            },
        )
        applied.append(f"equipment '{item.display_name}' recorded (verified)")

    elif screen_type == "gear_detail":
        from game_companion.core.equipment.service import GearService

        gear = GearService(session, adapter)
        item = gear.create(
            game_id,
            player_id,
            {
                "slot": candidate.get("slot"),
                "set_key": candidate.get("set_key"),
                "rarity": candidate.get("rarity"),
                "level": candidate.get("level"),
                "main_stat_key": candidate.get("main_stat_key"),
                "main_stat_value": candidate.get("main_stat_value"),
                "substats": candidate.get("substats") or [],
                "character": character.key if character else None,
                "verified": True,
                "source": "screenshot_import",
            },
        )
        applied.append(f"gear item {item.id} recorded (verified)")

    elif screen_type in ("gear_list", "resources"):
        raise ValidationError(
            f"'{screen_type}' candidates are informational; confirm individual "
            "gear_detail / resource screens to store data"
        )
    return applied
