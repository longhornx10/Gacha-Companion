"""Team and resource routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from game_companion.api.deps import adapter_for, get_db, resolve_player
from game_companion.api.schemas.requests import PlanPut, ResourcePut, TeamSave, TeamUpdate
from game_companion.api.serialize import plan_entry_dict, team_dict
from game_companion.core.resources.service import ResourceService
from game_companion.core.teams.service import TeamService
from game_companion.db.repositories import CharacterRepository, ResourceRepository, TeamRepository

router = APIRouter(prefix="/games/{game_id}")


# -- teams ---------------------------------------------------------------------


@router.get("/teams")
def list_teams(game_id: str, session: Session = Depends(get_db), player=Depends(resolve_player)):
    by_id = {c.id: c for c in CharacterRepository(session).search(game_id, player.id)}
    teams = TeamRepository(session).list_all(game_id=game_id, player_profile_id=player.id)
    return {"teams": [team_dict(t, by_id) for t in teams]}


@router.post("/teams", status_code=201)
def save_team(game_id: str, payload: TeamSave, session: Session = Depends(get_db), player=Depends(resolve_player)):
    service = TeamService(session, adapter_for(game_id))
    team = service.save_team(
        game_id, player.id, payload.name, payload.members,
        notes=payload.notes, is_active=payload.is_active,
    )
    by_id = {c.id: c for c in CharacterRepository(session).search(game_id, player.id)}
    return team_dict(team, by_id)


@router.get("/teams/{team_id}")
def get_team(game_id: str, team_id: str, session: Session = Depends(get_db), player=Depends(resolve_player)):
    team = TeamRepository(session).get_or_raise(team_id, "team")
    from game_companion.errors import NotFoundError

    if team.game_id != game_id or team.player_profile_id != player.id:
        raise NotFoundError("team not found for this player/game")
    by_id = {c.id: c for c in CharacterRepository(session).search(game_id, player.id)}
    return team_dict(team, by_id)


@router.patch("/teams/{team_id}")
def update_team(game_id: str, team_id: str, payload: TeamUpdate, session: Session = Depends(get_db), player=Depends(resolve_player)):
    from game_companion.errors import NotFoundError

    service = TeamService(session, adapter_for(game_id))
    team = TeamRepository(session).get_or_raise(team_id, "team")
    if team.game_id != game_id or team.player_profile_id != player.id:
        raise NotFoundError("team not found for this player/game")
    name = payload.name or team.name
    members = payload.members if payload.members is not None else [
        {"character": m.character_id, "position": m.position, "role": m.role} for m in team.members
    ]
    team = service.save_team(
        game_id, player.id, name, members, notes=payload.notes, is_active=payload.is_active
    )
    by_id = {c.id: c for c in CharacterRepository(session).search(game_id, player.id)}
    return team_dict(team, by_id)


@router.delete("/teams/{team_id}")
def delete_team(game_id: str, team_id: str, session: Session = Depends(get_db), player=Depends(resolve_player)):
    from game_companion.errors import NotFoundError

    repo = TeamRepository(session)
    team = repo.get_or_raise(team_id, "team")
    if team.game_id != game_id or team.player_profile_id != player.id:
        raise NotFoundError("team not found for this player/game")
    repo.delete(team)
    return {"deleted": team_id}


@router.post("/teams/{team_id}/activate")
def activate_team(game_id: str, team_id: str, session: Session = Depends(get_db), player=Depends(resolve_player)):
    from game_companion.errors import NotFoundError

    service = TeamService(session, adapter_for(game_id))
    team = TeamRepository(session).get_or_raise(team_id, "team")
    if team.game_id != game_id or team.player_profile_id != player.id:
        raise NotFoundError("team not found for this player/game")
    return service.activate_team(team)


@router.post("/teams/{team_id}/deactivate")
def deactivate_team(game_id: str, team_id: str, session: Session = Depends(get_db), player=Depends(resolve_player)):
    from game_companion.errors import NotFoundError

    repo = TeamRepository(session)
    team = repo.get_or_raise(team_id, "team")
    if team.game_id != game_id or team.player_profile_id != player.id:
        raise NotFoundError("team not found for this player/game")
    team.is_active = False
    session.flush()
    return {"team_id": team.id, "active": False}


# -- resources -------------------------------------------------------------------


@router.get("/resources")
def list_resources(game_id: str, session: Session = Depends(get_db), player=Depends(resolve_player)):
    service = ResourceService(session, adapter_for(game_id))
    rows = service.list_with_status(game_id, player.id)
    return {
        "resources": rows,
        "legend": {
            "done": "white — covers all planned targets",
            "prep": "cyan/lime — covers one full character, working toward the rest",
            "very_low": "orange — below one character's max",
            "critically_low": "red — far below one character's max",
            "unknown": "gray — requirement data missing; nothing is guessed",
        },
    }


@router.get("/resources/status/{resource_key}")
def resource_status(game_id: str, resource_key: str, session: Session = Depends(get_db), player=Depends(resolve_player)):
    service = ResourceService(session, adapter_for(game_id))
    return service.evaluate_key(game_id, player.id, resource_key)


@router.put("/resources/{resource_key}")
def put_resource(game_id: str, resource_key: str, payload: ResourcePut, session: Session = Depends(get_db), player=Depends(resolve_player)):
    repo = ResourceRepository(session)
    row = repo.upsert(game_id, player.id, resource_key, payload.quantity)
    if payload.notes is not None:
        row.notes = payload.notes
    service = ResourceService(session, adapter_for(game_id))
    return service.evaluate_key(game_id, player.id, resource_key)


@router.get("/resources/plan/{resource_key}")
def get_plan(game_id: str, resource_key: str, session: Session = Depends(get_db), player=Depends(resolve_player)):
    entries = ResourceRepository(session).plan_entries(game_id, player.id, resource_key)
    return {"plan": [plan_entry_dict(e) for e in entries]}


@router.put("/resources/plan/{resource_key}")
def put_plan(game_id: str, resource_key: str, payload: PlanPut, session: Session = Depends(get_db), player=Depends(resolve_player)):
    repo = ResourceRepository(session)
    chars = CharacterRepository(session)
    repo.clear_plan(game_id, player.id, resource_key)
    saved = []
    for entry in payload.entries:
        character_id = None
        if entry.get("character"):
            char = chars.get(str(entry["character"]))
            if char is not None and char.game_id == game_id and char.player_profile_id == player.id:
                character_id = char.id
            else:
                character_id = chars.get_by_key_or_raise(game_id, player.id, str(entry["character"])).id
        row = repo.set_plan_entry(game_id, player.id, resource_key, character_id, int(entry.get("amount", 0)))
        saved.append(plan_entry_dict(row))
    service = ResourceService(session, adapter_for(game_id))
    return {"plan": saved, "status": service.evaluate_key(game_id, player.id, resource_key)}


@router.delete("/resources/plan/{resource_key}")
def delete_plan(game_id: str, resource_key: str, session: Session = Depends(get_db), player=Depends(resolve_player)):
    ResourceRepository(session).clear_plan(game_id, player.id, resource_key)
    return {"cleared": resource_key}
