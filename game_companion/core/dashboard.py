"""Dashboard aggregate: one read-only snapshot per game+player for the UI.

Pure aggregation over existing repositories — no business logic, no LLM.
The same shape backs ``GET /api/dashboard`` and the ``/ui`` dashboard page.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from game_companion.core.codes.service import CodeService
from game_companion.core.games.base import GameAdapter
from game_companion.core.resources.service import ResourceService
from game_companion.db.models import Character
from game_companion.db.repositories import (
    CharacterRepository,
    EquipmentRepository,
    GearRepository,
    HistoryRepository,
    ImportRepository,
    TeamRepository,
)
from game_companion.utils import to_iso


def _freshness(chars: list[Character]) -> str | None:
    stamps = [c.last_verified_at for c in chars if c.last_verified_at is not None]
    return to_iso(min(stamps)) if stamps else None


def build_dashboard(session: Session, adapter: GameAdapter, player_id: str) -> dict:
    game_id = adapter.game_id
    characters = CharacterRepository(session).search(game_id, player_id)
    owned = [c for c in characters if c.owned]
    teams = TeamRepository(session).list_all(game_id=game_id, player_profile_id=player_id)
    active_team = next((t for t in teams if t.is_active), None)
    by_id = {c.id: c for c in characters}
    imports = ImportRepository(session).list_all(game_id=game_id, player_profile_id=player_id)
    last_import = max(imports, key=lambda i: i.created_at, default=None)
    active_codes = [
        row for row, _state in CodeService(session, adapter).list_codes(player_id)
        if row.status == "active"
    ]
    return {
        "game_id": game_id,
        "game_name": adapter.display_name,
        "roster_count": len(owned),
        "roster_total": len(characters),
        "gear_count": len(GearRepository(session).search(game_id, player_id)),
        "equipment_count": len(EquipmentRepository(session).search(game_id, player_id)),
        "codes_active": len(active_codes),
        "last_import": (
            {"status": last_import.status, "screen_type": last_import.screen_type,
             "created_at": to_iso(last_import.created_at)}
            if last_import
            else None
        ),
        "data_freshness": _freshness(characters),
        "active_team": _team_dict(active_team, by_id),
        "resources": ResourceService(session, adapter).list_with_status(game_id, player_id),
        "recent_results": [
            {
                "encounter_key": r.encounter_key,
                "cleared": r.cleared,
                "stars": r.stars,
                "score": r.score,
                "played_at": to_iso(r.played_at),
            }
            for r in HistoryRepository(session).results(game_id, player_id)[:5]
        ],
    }


def _team_dict(team, by_id: dict[str, Character]) -> dict | None:
    if team is None:
        return None
    members = []
    for m in team.members:
        character = by_id.get(m.character_id)
        members.append(
            {
                "position": m.position,
                "key": character.key if character else None,
                "display_name": character.display_name if character else m.character_id,
            }
        )
    return {"id": team.id, "name": team.name, "members": members}
