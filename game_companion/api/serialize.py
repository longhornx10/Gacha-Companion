"""Serializers turning ORM rows into JSON-friendly dicts."""

from __future__ import annotations

from typing import Any

from game_companion.db.models import (
    Character,
    CharacterBuild,
    CombatResult,
    EquipmentItem,
    GearItem,
    PlayerCodeState,
    PlayerProfile,
    RedeemCode,
    ResearchClaim,
    ResearchSource,
    Resource,
    ResourcePlanEntry,
    ScreenshotImport,
    Team,
    TrainingGoal,
    TrainingIssue,
)
from game_companion.utils import to_iso


def profile_dict(p: PlayerProfile) -> dict:
    return {
        "id": p.id,
        "display_name": p.display_name,
        "notes": p.notes,
        "created_at": to_iso(p.created_at),
    }


def character_dict(c: Character) -> dict:
    return {
        "id": c.id,
        "game_id": c.game_id,
        "key": c.key,
        "display_name": c.display_name,
        "rarity": c.rarity,
        "owned": c.owned,
        "level": c.level,
        "duplication_level": c.duplication_level,
        "favorite": c.favorite,
        "notes": c.notes,
        "data": c.data,
        "source": c.source,
        "last_verified_at": to_iso(c.last_verified_at),
        "skills": {s.skill_key: s.level for s in c.skills},
    }


def build_dict(b: CharacterBuild) -> dict:
    return {
        "id": b.id,
        "character_id": b.character_id,
        "name": b.name,
        "is_active": b.is_active,
        "equipment_item_id": b.equipment_item_id,
        "gear_slots": {row.slot: row.gear_item_id for row in b.gear_slots},
        "notes": b.notes,
    }


def equipment_dict(i: EquipmentItem) -> dict:
    return _row(i, skip={"player_profile_id"})


def gear_dict(g: GearItem) -> dict:
    return _row(g, skip={"player_profile_id"})


def team_dict(t: Team, characters_by_id: dict[str, Character] | None = None) -> dict:
    members = []
    for m in t.members:
        entry: dict[str, Any] = {
            "character_id": m.character_id,
            "position": m.position,
            "role": m.role,
        }
        if characters_by_id and m.character_id in characters_by_id:
            entry["key"] = characters_by_id[m.character_id].key
            entry["display_name"] = characters_by_id[m.character_id].display_name
        members.append(entry)
    return {
        "id": t.id,
        "name": t.name,
        "is_active": t.is_active,
        "notes": t.notes,
        "members": members,
    }


def resource_dict(r: Resource) -> dict:
    return _row(r, skip={"player_profile_id"})


def plan_entry_dict(e: ResourcePlanEntry) -> dict:
    return {"resource_key": e.resource_key, "character_id": e.character_id, "amount": e.amount}


def code_dict(c: RedeemCode, state: PlayerCodeState | None = None) -> dict:
    return {
        "id": c.id,
        "code": c.code,
        "status": c.status,
        "expires_at": to_iso(c.expires_at),
        "discovered_at": to_iso(c.discovered_at),
        "notes": c.notes,
        "used": bool(state and state.used),
        "used_at": to_iso(state.used_at) if state else None,
    }


def combat_result_dict(r: CombatResult) -> dict:
    return _row(r, skip={"player_profile_id"})


def training_issue_dict(i: TrainingIssue) -> dict:
    return _row(i, skip={"player_profile_id"})


def training_goal_dict(g: TrainingGoal) -> dict:
    return _row(g, skip={"player_profile_id"})


def source_dict(s: ResearchSource) -> dict:
    return _row(s, skip={"id"})


def claim_dict(c: ResearchClaim) -> dict:
    return {
        "id": c.id,
        "subject": c.subject,
        "claim_type": c.claim_type,
        "content": c.content,
        "confidence": c.confidence,
        "retrieved_at": to_iso(c.retrieved_at),
        "evidence": c.evidence,
        "source_id": c.source_id,
    }


def import_dict(i: ScreenshotImport) -> dict:
    return {
        "id": i.id,
        "game_id": i.game_id,
        "screen_type": i.screen_type,
        "status": i.status,
        "candidate": i.candidate,
        "diff": i.diff,
        "confidence": i.confidence,
        "extracted_fields": i.extracted_fields,
        "rejected_fields": i.rejected_fields,
        "applied_at": to_iso(i.applied_at),
        "error": i.error,
        "screenshot_name": i.screenshot_name,
        "created_at": to_iso(i.created_at),
    }


def _row(obj: Any, *, skip: set[str] = frozenset()) -> dict:
    out = {}
    for column in obj.__table__.columns:
        if column.name in skip:
            continue
        value = getattr(obj, column.name)
        out[column.name] = to_iso(value) if hasattr(value, "tzinfo") else value
    return out
