"""System routes: health, games registry, players, preferences."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from game_companion.api.deps import get_db, resolve_player
from game_companion.api.schemas.requests import PlayerCreate, PlayerUpdate, PreferencePut
from game_companion.api.serialize import profile_dict
from game_companion.core.games.registry import adapter_ids, list_adapters
from game_companion.db.models import PlayerProfile
from game_companion.db.repositories import PlayerRepository

router = APIRouter()


@router.get("/health")
def health(request: Request):
    return {
        "status": "ok",
        "service": "gacha-companion",
        "games": adapter_ids(),
    }


@router.get("/games")
def list_games():
    out = []
    for adapter in list_adapters():
        term = adapter.terminology()
        out.append(
            {
                "game_id": adapter.game_id,
                "display_name": adapter.display_name,
                "version": adapter.version,
                "terminology": {
                    "character": term.character,
                    "equipment": term.equipment,
                    "gear": term.gear,
                    "duplication": term.duplication,
                    "special_progression": term.special_progression,
                },
                "team_rules": {"min_size": adapter.team_rules().min_size, "max_size": adapter.team_rules().max_size},
                "gear_slots": [s.key for s in adapter.gear_slots()],
                "encounter_modes": [
                    {"key": m.key, "name": m.name, "slot_count": m.slot_count}
                    for m in adapter.encounter_modes()
                ],
                "screenshot_types": sorted(adapter.screenshot_specs()),
            }
        )
    return {"games": out}


@router.get("/games/{game_id}")
def get_game(game_id: str):
    from game_companion.api.deps import adapter_for

    a = adapter_for(game_id)
    term = a.terminology()
    return {
        "game_id": a.game_id,
        "display_name": a.display_name,
        "version": a.version,
        "terminology": {
            "character": term.character,
            "equipment": term.equipment,
            "gear": term.gear,
            "duplication": term.duplication,
            "special_progression": term.special_progression,
        },
        "team_rules": {"min_size": a.team_rules().min_size, "max_size": a.team_rules().max_size},
        "gear_slots": [
            {"key": s.key, "name": s.name, "main_stat_pool": list(s.main_stat_pool)}
            for s in a.gear_slots()
        ],
        "stats": [{"key": s.key, "name": s.name, "kind": s.kind} for s in a.stat_definitions()],
        "skills": [
            {"key": s.key, "name": s.name, "max_level": s.max_level, "note": s.max_level_note}
            for s in a.skill_definitions()
        ],
        "resources": [
            {"key": r.key, "name": r.name, "single_character_max": r.single_character_max}
            for r in a.resource_definitions()
        ],
        "encounter_modes": [
            {"key": m.key, "name": m.name, "slot_count": m.slot_count, "description": m.description}
            for m in a.encounter_modes()
        ],
        "sources": [
            {"key": s.key, "name": s.name, "url": s.url, "category": s.category, "trust": s.trust}
            for s in a.source_registry()
        ],
        "screenshot_types": sorted(a.screenshot_specs()),
        "code_config": a.code_config(),
    }


# -- players ------------------------------------------------------------------


@router.post("/players", status_code=201)
def create_player(payload: PlayerCreate, session: Session = Depends(get_db)):
    profile = PlayerRepository(session).add(
        PlayerProfile(display_name=payload.display_name, notes=payload.notes)
    )
    return profile_dict(profile)


@router.get("/players")
def list_players(session: Session = Depends(get_db)):
    return {"players": [profile_dict(p) for p in PlayerRepository(session).list_all()]}


@router.get("/players/{player_id}")
def get_player(player_id: str, session: Session = Depends(get_db)):
    return profile_dict(PlayerRepository(session).get_or_raise(player_id, "player"))


@router.patch("/players/{player_id}")
def update_player(player_id: str, payload: PlayerUpdate, session: Session = Depends(get_db)):
    profile = PlayerRepository(session).get_or_raise(player_id, "player")
    if payload.display_name is not None:
        profile.display_name = payload.display_name
    if payload.notes is not None:
        profile.notes = payload.notes
    return profile_dict(profile)


@router.delete("/players/{player_id}")
def delete_player(player_id: str, session: Session = Depends(get_db)):
    repo = PlayerRepository(session)
    profile = repo.get_or_raise(player_id, "player")
    repo.delete(profile)
    return {"deleted": player_id}


# -- preferences ---------------------------------------------------------------


@router.get("/players/{player_id}/preferences")
def list_preferences(
    player_id: str, scope: str | None = None, session: Session = Depends(get_db)
):
    PlayerRepository(session).get_or_raise(player_id, "player")
    prefs = PlayerRepository(session).list_preferences(player_id, scope)
    return {
        "preferences": {f"{p.scope}:{p.key}": p.value for p in prefs},
        "items": [{"scope": p.scope, "key": p.key, "value": p.value} for p in prefs],
    }


@router.put("/players/{player_id}/preferences/{scope}/{key:path}")
def put_preference(
    player_id: str,
    scope: str,
    key: str,
    payload: PreferencePut,
    session: Session = Depends(get_db),
    _player: None = Depends(resolve_player),
):
    pref = PlayerRepository(session).set_preference(player_id, scope, key, payload.value)
    return {"scope": pref.scope, "key": pref.key, "value": pref.value}


@router.get("/me/preferences")
def my_preferences(
    scope: str | None = None,
    session: Session = Depends(get_db),
    player=Depends(resolve_player),
):
    return list_preferences(player.id, scope, session)
