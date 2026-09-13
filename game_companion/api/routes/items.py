"""Equipment and gear routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from game_companion.api.deps import adapter_for, get_db, resolve_player
from game_companion.api.schemas.requests import (
    EquipmentCreate,
    EquipmentUpdate,
    GearCreate,
    GearEvaluateRequest,
    GearUpdate,
)
from game_companion.api.serialize import equipment_dict, gear_dict
from game_companion.core.equipment.service import EquipmentService, GearService
from game_companion.db.repositories import CharacterRepository, GearRepository

router = APIRouter(prefix="/games/{game_id}")

# -- equipment (W-Engines / Light Cones / Sigils...) ---------------------------


@router.get("/equipment")
def list_equipment(
    game_id: str,
    character: str | None = Query(default=None),
    session: Session = Depends(get_db),
    player=Depends(resolve_player),
):
    service = EquipmentService(session, adapter_for(game_id))
    items = service.equipment.search(game_id, player.id)
    if character:
        char = service.characters.get_by_key_or_raise(game_id, player.id, character)
        items = [i for i in items if i.equipped_character_id == char.id]
    return {"equipment": [equipment_dict(i) for i in items]}


@router.post("/equipment", status_code=201)
def create_equipment(
    game_id: str,
    payload: EquipmentCreate,
    session: Session = Depends(get_db),
    player=Depends(resolve_player),
):
    service = EquipmentService(session, adapter_for(game_id))
    item = service.create(game_id, player.id, payload.model_dump(exclude_unset=True))
    return equipment_dict(item)


@router.get("/equipment/{item_id}")
def get_equipment(
    game_id: str, item_id: str, session: Session = Depends(get_db), player=Depends(resolve_player)
):
    service = EquipmentService(session, adapter_for(game_id))
    return equipment_dict(service.equipment.get_or_raise(item_id, "equipment item"))


@router.patch("/equipment/{item_id}")
def update_equipment(
    game_id: str,
    item_id: str,
    payload: EquipmentUpdate,
    session: Session = Depends(get_db),
    player=Depends(resolve_player),
):
    service = EquipmentService(session, adapter_for(game_id))
    item = service.equipment.get_or_raise(item_id, "equipment item")
    item = service.update(item, payload.model_dump(exclude_unset=True))
    return equipment_dict(item)


@router.delete("/equipment/{item_id}")
def delete_equipment(
    game_id: str, item_id: str, session: Session = Depends(get_db), player=Depends(resolve_player)
):
    service = EquipmentService(session, adapter_for(game_id))
    item = service.equipment.get_or_raise(item_id, "equipment item")
    service.equipment.delete(item)
    return {"deleted": item_id}


# -- gear (Drive Discs / Relics / Charms...) ------------------------------------


@router.get("/gear")
def list_gear(
    game_id: str,
    character: str | None = Query(default=None),
    set_key: str | None = Query(default=None),
    slot: str | None = Query(default=None),
    favorite: bool | None = Query(default=None),
    locked: bool | None = Query(default=None),
    session: Session = Depends(get_db),
    player=Depends(resolve_player),
):
    service = GearService(session, adapter_for(game_id))
    items = service.gear.search(
        game_id, player.id, set_key=set_key, slot=slot, favorite=favorite, locked=locked
    )
    if character:
        char = service.characters.get_by_key_or_raise(game_id, player.id, character)
        items = [g for g in items if g.equipped_character_id == char.id]
    return {
        "gear_noun": adapter_for(game_id).terminology().gear,
        "gear": [gear_dict(g) for g in items],
    }


@router.post("/gear", status_code=201)
def create_gear(
    game_id: str,
    payload: GearCreate,
    session: Session = Depends(get_db),
    player=Depends(resolve_player),
):
    service = GearService(session, adapter_for(game_id))
    item = service.create(game_id, player.id, payload.model_dump(exclude_unset=True))
    return gear_dict(item)


@router.get("/gear/{item_id}")
def get_gear(
    game_id: str, item_id: str, session: Session = Depends(get_db), player=Depends(resolve_player)
):
    service = GearService(session, adapter_for(game_id))
    return gear_dict(service.gear.get_or_raise(item_id, "gear item"))


@router.patch("/gear/{item_id}")
def update_gear(
    game_id: str,
    item_id: str,
    payload: GearUpdate,
    session: Session = Depends(get_db),
    player=Depends(resolve_player),
):
    service = GearService(session, adapter_for(game_id))
    item = service.gear.get_or_raise(item_id, "gear item")
    item = service.update(item, payload.model_dump(exclude_unset=True))
    return gear_dict(item)


@router.delete("/gear/{item_id}")
def delete_gear(
    game_id: str, item_id: str, session: Session = Depends(get_db), player=Depends(resolve_player)
):
    service = GearService(session, adapter_for(game_id))
    item = service.gear.get_or_raise(item_id, "gear item")
    service.gear.delete(item)
    return {"deleted": item_id}


@router.post("/gear/{item_id}/evaluate")
def evaluate_gear(
    game_id: str,
    item_id: str,
    payload: GearEvaluateRequest,
    session: Session = Depends(get_db),
    player=Depends(resolve_player),
):
    from game_companion.core.recommendations.gear_eval import evaluate_gear_item

    adapter = adapter_for(game_id)
    gear_row = GearRepository(session).get_or_raise(item_id, "gear item")
    character = None
    if payload.character:
        character = CharacterRepository(session).get_by_key_or_raise(game_id, player.id, payload.character)
    return evaluate_gear_item(session, adapter, game_id, player.id, gear_row, character)
