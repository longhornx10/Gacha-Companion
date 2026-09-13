"""Roster routes: characters, skills, builds."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from game_companion.api.deps import adapter_for, get_db, resolve_player
from game_companion.api.schemas.requests import (
    BuildCreate,
    BuildSlotPut,
    BuildUpdate,
    CharacterCreate,
    CharacterUpdate,
    SkillsPut,
)
from game_companion.api.serialize import build_dict, character_dict
from game_companion.core.roster.service import RosterService
from game_companion.db.repositories import CharacterRepository

router = APIRouter(prefix="/games/{game_id}/characters")


def _service(session: Session, game_id: str) -> tuple[RosterService, str]:
    return RosterService(session, adapter_for(game_id)), game_id


@router.get("")
def list_characters(
    game_id: str,
    owned: bool | None = Query(default=None),
    favorite: bool | None = Query(default=None),
    session: Session = Depends(get_db),
    player=Depends(resolve_player),
):
    adapter = adapter_for(game_id)
    chars = CharacterRepository(session).search(
        game_id, player.id, owned=owned, favorite=favorite
    )
    return {
        "game": adapter.display_name,
        "character_noun": adapter.terminology().character,
        "characters": [character_dict(c) for c in chars],
    }


@router.post("", status_code=201)
def create_character(
    game_id: str,
    payload: CharacterCreate,
    session: Session = Depends(get_db),
    player=Depends(resolve_player),
):
    service, _ = _service(session, game_id)
    char = service.create_character(game_id, player.id, payload.model_dump())
    return character_dict(char)


@router.get("/{ref}")
def get_character(
    game_id: str,
    ref: str,
    session: Session = Depends(get_db),
    player=Depends(resolve_player),
):
    service, _ = _service(session, game_id)
    char = service.resolve_character(game_id, player.id, ref)
    out = character_dict(char)
    out["builds"] = [build_dict(b) for b in service.builds.for_character(char.id)]
    return out


@router.patch("/{ref}")
def update_character(
    game_id: str,
    ref: str,
    payload: CharacterUpdate,
    session: Session = Depends(get_db),
    player=Depends(resolve_player),
):
    service, _ = _service(session, game_id)
    char = service.resolve_character(game_id, player.id, ref)
    char = service.update_character(char, payload.model_dump(exclude_unset=True))
    return character_dict(char)


@router.delete("/{ref}")
def delete_character(
    game_id: str,
    ref: str,
    session: Session = Depends(get_db),
    player=Depends(resolve_player),
):
    service, _ = _service(session, game_id)
    char = service.resolve_character(game_id, player.id, ref)
    CharacterRepository(session).delete(char)
    return {"deleted": char.key}


@router.put("/{ref}/skills")
def set_skills(
    game_id: str,
    ref: str,
    payload: SkillsPut,
    session: Session = Depends(get_db),
    player=Depends(resolve_player),
):
    service, _ = _service(session, game_id)
    char = service.resolve_character(game_id, player.id, ref)
    result = service.set_skills(char, payload.skills)
    return {"character": char.key, "skills": result}


# -- builds --------------------------------------------------------------------


@router.get("/{ref}/builds")
def list_builds(
    game_id: str, ref: str, session: Session = Depends(get_db), player=Depends(resolve_player)
):
    service, _ = _service(session, game_id)
    char = service.resolve_character(game_id, player.id, ref)
    return {"builds": [build_dict(b) for b in service.builds.for_character(char.id)]}


@router.post("/{ref}/builds", status_code=201)
def create_build(
    game_id: str,
    ref: str,
    payload: BuildCreate,
    session: Session = Depends(get_db),
    player=Depends(resolve_player),
):
    service, _ = _service(session, game_id)
    char = service.resolve_character(game_id, player.id, ref)
    build = service.create_build(
        char, payload.name, notes=payload.notes, set_active=payload.set_active
    )
    return build_dict(build)


def _get_build(service: RosterService, game_id: str, player_id: str, build_id: str):
    build = service.builds.get_or_raise(build_id, "build")
    if build.game_id != game_id or build.player_profile_id != player_id:
        from game_companion.errors import NotFoundError

        raise NotFoundError("build not found for this player/game")
    return build


@router.get("/{ref}/builds/{build_id}")
def get_build(
    game_id: str,
    ref: str,
    build_id: str,
    session: Session = Depends(get_db),
    player=Depends(resolve_player),
):
    service, _ = _service(session, game_id)
    _char = service.resolve_character(game_id, player.id, ref)
    build = _get_build(service, game_id, player.id, build_id)
    return build_dict(build)


@router.patch("/{ref}/builds/{build_id}")
def update_build(
    game_id: str,
    ref: str,
    build_id: str,
    payload: BuildUpdate,
    session: Session = Depends(get_db),
    player=Depends(resolve_player),
):
    service, _ = _service(session, game_id)
    service.resolve_character(game_id, player.id, ref)
    build = _get_build(service, game_id, player.id, build_id)
    if payload.notes is not None:
        build.notes = payload.notes
    if payload.equipment_item_id is not None or payload.unset_equipment:
        service.set_build_equipment(
            build, None if payload.unset_equipment else payload.equipment_item_id
        )
    session.flush()
    return build_dict(build)


@router.put("/{ref}/builds/{build_id}/slots")
def set_build_slot(
    game_id: str,
    ref: str,
    build_id: str,
    payload: BuildSlotPut,
    session: Session = Depends(get_db),
    player=Depends(resolve_player),
):
    service, _ = _service(session, game_id)
    service.resolve_character(game_id, player.id, ref)
    build = _get_build(service, game_id, player.id, build_id)
    result = service.set_build_slot(build, payload.slot, payload.gear_item_id)
    return result


@router.post("/{ref}/builds/{build_id}/activate")
def activate_build(
    game_id: str,
    ref: str,
    build_id: str,
    session: Session = Depends(get_db),
    player=Depends(resolve_player),
):
    service, _ = _service(session, game_id)
    service.resolve_character(game_id, player.id, ref)
    build = _get_build(service, game_id, player.id, build_id)
    return service.activate_build(build)
