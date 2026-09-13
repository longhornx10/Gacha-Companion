"""Roster audit (M14) and upgrade/farming planner (M13) — deterministic rules."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy.orm import Session

from game_companion.core.games.base import GameAdapter
from game_companion.core.teams.scoring import build_readiness
from game_companion.db.models import AuditResult, Character
from game_companion.db.repositories import (
    AuditRepository,
    BuildRepository,
    CharacterRepository,
    TeamRepository,
)
from game_companion.utils import to_iso, utcnow

STALE_AFTER_DAYS = 30


def audit_roster(
    session: Session,
    adapter: GameAdapter,
    game_id: str,
    player_id: str,
    character: Character | None = None,
) -> dict:
    chars = [character] if character else CharacterRepository(session).search(
        game_id, player_id, owned=True
    )
    progression = adapter.progression_rules()
    level_cap = (progression.get("level_cap") or {}).get("value")
    skill_targets = progression.get("skill_targets") or {}
    gear_slots_total = max(len(adapter.gear_slots()), 1)

    results = []
    audit_repo = AuditRepository(session)
    for char in chars:
        issues: list[dict[str, str]] = []
        term = adapter.terminology()
        if char.level is None:
            issues.append({"code": "missing_level", "detail": f"{term.character} level unknown"})
        elif level_cap and char.level < 0.8 * level_cap:
            issues.append({
                "code": "level_below_cap",
                "detail": f"level {char.level} vs cap {level_cap} (starter data)",
            })
        skill_levels = {s.skill_key: s.level for s in char.skills}
        for skill_key, target in skill_targets.items():
            target_level = target.get("target")
            current = skill_levels.get(skill_key)
            if current is None:
                issues.append({
                    "code": "missing_skill",
                    "detail": f"skill '{skill_key}' level unknown (target {target_level})",
                })
            elif target_level and current < target_level:
                issues.append({
                    "code": "skill_below_target",
                    "detail": f"skill '{skill_key}' {current} < target {target_level} (starter data)",
                })
        readiness = build_readiness(session, adapter, char)
        if readiness.value < 6.0:
            issues.append({"code": "build_incomplete", "detail": readiness.detail or "build incomplete"})
        else:
            active = BuildRepository(session).active_for_character(char.id)
            if active is not None:
                filled = sum(1 for row in active.gear_slots if row.gear_item_id)
                if filled < gear_slots_total:
                    issues.append({
                        "code": "gear_slots_unfilled",
                        "detail": f"{filled}/{gear_slots_total} gear slots filled",
                    })
        if char.last_verified_at is None:
            issues.append({
                "code": "never_verified",
                "detail": "stored data never verified against a screenshot",
            })
        elif char.last_verified_at < utcnow() - timedelta(days=STALE_AFTER_DAYS):
            issues.append({
                "code": "stale_data",
                "detail": f"last verified {to_iso(char.last_verified_at)} "
                          f"(> {STALE_AFTER_DAYS} days ago)",
            })
        status = "ok" if not issues else ("attention" if len(issues) <= 2 else "critical")
        row = audit_repo.add(
            AuditResult(
                game_id=game_id,
                player_profile_id=player_id,
                character_id=char.id,
                status=status,
                issues=issues,
                checked_at=utcnow(),
            )
        )
        results.append({
            "character": char.key,
            "display_name": char.display_name,
            "status": status,
            "issues": issues,
            "audit_id": row.id,
        })
    return {
        "audited": len(results),
        "results": sorted(results, key=lambda r: ({"critical": 0, "attention": 1, "ok": 2}[r["status"]], r["character"])),
    }


def build_upgrade_plan(
    session: Session,
    adapter: GameAdapter,
    game_id: str,
    player_id: str,
) -> dict:
    """Prioritized, reasoned upgrade actions. Honest about unknown data."""
    from game_companion.core.resources.service import ResourceService

    chars = CharacterRepository(session).search(game_id, player_id, owned=True)
    active_members: set[str] = set()
    for team in TeamRepository(session).active_teams(game_id, player_id):
        for m in team.members:
            char = CharacterRepository(session).get(m.character_id)
            if char:
                active_members.add(char.key)

    progression = adapter.progression_rules()
    skill_targets = progression.get("skill_targets") or {}

    actions: list[dict[str, Any]] = []
    for char in chars:
        priority = 5.0 + (3.0 if char.key in active_members else 0.0) + (1.0 if char.favorite else 0.0)
        skill_levels = {s.skill_key: s.level for s in char.skills}
        for skill_key, target in skill_targets.items():
            target_level = target.get("target")
            current = skill_levels.get(skill_key)
            if current is not None and target_level and current < target_level:
                actions.append({
                    "character": char.key,
                    "action": f"level {skill_key} {current} -> {target_level}",
                    "priority": priority + 1.5,
                    "reason": "skill below target (starter targets; verify in-game)",
                })
        if char.level is not None and (progression.get("level_cap") or {}).get("value"):
            cap = progression["level_cap"]["value"]
            if char.level < cap:
                actions.append({
                    "character": char.key,
                    "action": f"raise level {char.level} -> {cap}",
                    "priority": priority + 1.0,
                    "reason": "level below cap (starter cap data)",
                })
        readiness = build_readiness(session, adapter, char)
        if readiness.value < 8.0:
            actions.append({
                "character": char.key,
                "action": "complete build (equipment/gear)",
                "priority": priority + 2.0,
                "reason": readiness.detail or "build incomplete",
            })

    actions.sort(key=lambda a: (-a["priority"], a["character"], a["action"]))

    # Resource framing: which tracked resources could fund these actions.
    resource_rows = ResourceService(session, adapter).list_with_status(game_id, player_id)
    constrained = [r for r in resource_rows if r["status"] in ("critically_low", "very_low")]

    return {
        "actions": actions[:25],
        "resource_warnings": constrained,
        "honesty_note": (
            "Priorities derive from stored progression gaps and adapter starter data. "
            "Exact performance gains and verified material costs are not known, so none "
            "are claimed; fill resource requirements to unlock farming quantities."
        ),
    }
