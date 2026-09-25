"""Achievements: small, honest milestones computed from the player's own data.

Checks are pure reads over existing repositories; unlocking only ever inserts
a row recording *when* it happened. Nothing here gates features — it's delight.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from game_companion.core.games.base import GameAdapter
from game_companion.db.models import Achievement
from game_companion.db.repositories import (
    CharacterRepository,
    CodeRepository,
    EquipmentRepository,
    GearRepository,
    HistoryRepository,
)


@dataclass(frozen=True)
class AchievementDef:
    key: str
    name: str
    description: str
    icon: str  # emoji medal — no assets


def _owned_chars(session: Session, game_id: str, player_id: str):
    return CharacterRepository(session).search(game_id, player_id, owned=True)


def _gear(session: Session, game_id: str, player_id: str):
    return GearRepository(session).search(game_id, player_id)


def _equipment(session: Session, game_id: str, player_id: str):
    return EquipmentRepository(session).search(game_id, player_id)


def _full_builds(session: Session, game_id: str, player_id: str, slots_needed: int) -> int:
    by_char: dict[str, set[str | None]] = {}
    for g in _gear(session, game_id, player_id):
        if g.equipped_character_id:
            by_char.setdefault(g.equipped_character_id, set()).add(g.slot)
    engines = {
        e.equipped_character_id for e in _equipment(session, game_id, player_id)
        if e.equipped_character_id
    }
    count = 0
    for char_id, slots in by_char.items():
        if char_id in engines and len(slots) >= slots_needed:
            count += 1
    return count


def _used_codes(session: Session, game_id: str, player_id: str) -> int:
    repo = CodeRepository(session)
    count = 0
    for code in repo.list_all(game_id=game_id):
        state = repo.player_state(code.id, player_id)
        if state and state.used:
            count += 1
    return count


def _checks(session: Session, adapter: GameAdapter, player_id: str) -> dict[str, bool]:
    gid = adapter.game_id
    chars = _owned_chars(session, gid, player_id)
    gear = _gear(session, gid, player_id)
    used_codes = _used_codes(session, gid, player_id)
    cleared = [
        r for r in HistoryRepository(session).results(gid, player_id) if r.cleared
    ]
    verified = [c for c in chars if c.last_verified_at is not None]
    return {
        "first_recruit": len(chars) >= 1,
        "full_house": len(chars) >= 10,
        "legend_collector": len(chars) >= 25,
        "trust_verified": len(verified) >= 1,
        "auditor": len(verified) >= 10,
        "disc_hoarder": len(gear) >= 25,
        "dressed_for_battle": _full_builds(session, gid, player_id, 4) >= 1,
        "build_complete": _full_builds(session, gid, player_id, 6) >= 1,
        "code_hunter": used_codes >= 10,
        "first_clear": len(cleared) >= 1,
    }


DEFS: list[AchievementDef] = [
    AchievementDef("first_recruit", "First Recruit", "Add your first character", "🌱"),
    AchievementDef("full_house", "Full House", "Own 10 characters", "🏠"),
    AchievementDef("legend_collector", "Legend Collector", "Own 25 characters", "🏆"),
    AchievementDef("trust_verified", "Trust, Verified", "Verify a character's data", "✅"),
    AchievementDef("auditor", "Auditor", "Verify 10 characters", "🔍"),
    AchievementDef("disc_hoarder", "Disc Hoarder", "Log 25 pieces of set gear", "💿"),
    AchievementDef("dressed_for_battle", "Dressed for Battle", "Equip one character with an item and 4+ set pieces", "🧥"),
    AchievementDef("build_complete", "Build Complete", "A character with an item and all 6 set pieces", "💎"),
    AchievementDef("code_hunter", "Code Hunter", "Redeem 10 codes", "🎫"),
    AchievementDef("first_clear", "First Clear", "Log your first cleared fight", "⚔️"),
]

DEF_BY_KEY = {d.key: d for d in DEFS}


def check_and_unlock(session: Session, adapter: GameAdapter, player_id: str) -> tuple[list[dict], list[dict]]:
    """Evaluate every achievement; insert rows for the newly earned ones.

    Returns (all_states, newly_unlocked) — states in DEFS order with
    ``unlocked``/``unlocked_at``, newly as [{key, name, icon}].
    """
    gid = adapter.game_id
    results = _checks(session, adapter, player_id)
    existing = {
        row.key: row
        for row in session.execute(
            select(Achievement).where(
                Achievement.player_profile_id == player_id,
                Achievement.game_id == gid,
            )
        ).scalars()
    }
    from game_companion.utils import utcnow

    newly: list[dict] = []
    for d in DEFS:
        earned = results.get(d.key, False)
        row = existing.get(d.key)
        if earned and row is None:
            row = Achievement(
                player_profile_id=player_id, game_id=gid, key=d.key, unlocked_at=utcnow()
            )
            session.add(row)
            newly.append({"key": d.key, "name": d.name, "icon": d.icon})
    states = [
        {
            "key": d.key,
            "name": d.name,
            "description": d.description,
            "icon": d.icon,
            "unlocked": d.key in existing or any(n["key"] == d.key for n in newly),
            "unlocked_at": existing[d.key].unlocked_at if d.key in existing else None,
        }
        for d in DEFS
    ]
    return states, newly
