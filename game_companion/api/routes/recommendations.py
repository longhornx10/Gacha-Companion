"""Recommendations, optimizer and tutor routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from game_companion.api.deps import adapter_for, get_db, resolve_player
from game_companion.api.schemas.requests import (
    EquipmentCompareRequest,
    OptimizeRequest,
    TeamRecommendationRequest,
    TutorRequest,
)
from game_companion.core.coaching.tutor import explain as tutor_explain
from game_companion.core.recommendations.gear_eval import evaluate_inventory
from game_companion.core.recommendations.planner import audit_roster, build_upgrade_plan
from game_companion.core.recommendations.team_recs import compare_equipment, recommend_teams
from game_companion.core.roster.service import RosterService
from game_companion.core.teams.optimizer import optimize_team_allocation
from game_companion.core.teams.scoring import score_team_composition, viable_member_keys
from game_companion.db.repositories import EncounterRepository, PlayerRepository
from game_companion.errors import NotFoundError

router = APIRouter(prefix="/games/{game_id}")


@router.post("/recommendations/teams")
def team_recommendations(
    game_id: str,
    payload: TeamRecommendationRequest | None = None,
    session: Session = Depends(get_db),
    player=Depends(resolve_player),
):
    payload = payload or TeamRecommendationRequest()
    return recommend_teams(
        session, adapter_for(game_id), game_id, player.id,
        encounter=payload.encounter, count=payload.count,
    )


@router.post("/recommendations/gear-inventory")
def gear_inventory_evaluation(game_id: str, session: Session = Depends(get_db), player=Depends(resolve_player)):
    return evaluate_inventory(session, adapter_for(game_id), game_id, player.id)


@router.post("/recommendations/plan")
def upgrade_plan(game_id: str, session: Session = Depends(get_db), player=Depends(resolve_player)):
    return build_upgrade_plan(session, adapter_for(game_id), game_id, player.id)


@router.post("/recommendations/audit")
def run_audit(game_id: str, character: str | None = None, session: Session = Depends(get_db), player=Depends(resolve_player)):
    adapter = adapter_for(game_id)
    service = RosterService(session, adapter)
    char = None
    if character:
        char = service.resolve_character(game_id, player.id, character)
    return audit_roster(session, adapter, game_id, player.id, char)


@router.post("/recommendations/equipment-compare")
def equipment_compare(game_id: str, payload: EquipmentCompareRequest | None = None, session: Session = Depends(get_db), player=Depends(resolve_player)):
    payload = payload or EquipmentCompareRequest(character="")
    if not payload.character:
        from game_companion.errors import ValidationError

        raise ValidationError("provide 'character' (key or name) to compare equipment for")
    service = RosterService(session, adapter_for(game_id))
    char = service.resolve_character(game_id, player.id, payload.character)
    return compare_equipment(
        session, adapter_for(game_id), game_id, player.id, char, payload.item_ids
    )


@router.post("/recommendations/optimize")
def optimize(game_id: str, payload: OptimizeRequest | None = None, session: Session = Depends(get_db), player=Depends(resolve_player)):
    payload = payload or OptimizeRequest()
    adapter = adapter_for(game_id)
    encounter = EncounterRepository(session).find_by_key(game_id, payload.encounter_key)
    if encounter is None:
        known = {m.key: m for m in adapter.encounter_modes()}
        if payload.encounter_key not in known:
            raise NotFoundError(
                f"unknown encounter '{payload.encounter_key}' (define it via the encounters "
                "API or use an adapter mode)"
            )
        slot_count = known[payload.encounter_key].slot_count
        slot_constraints: list[dict] = [{} for _ in range(slot_count)]
    else:
        slot_count = max(len(encounter.slots), 1)
        slot_constraints = [slot.constraints or {} for slot in encounter.slots]
        slot_constraints += [{}] * (slot_count - len(slot_constraints))

    roster = viable_member_keys(session, game_id, player.id)
    team_size = adapter.team_rules().max_size
    preferences = {
        p.key: p.value
        for p in PlayerRepository(session).list_preferences(player.id)
        if p.scope in ("global", game_id)
    }
    comfort_weight = payload.comfort_weight
    if payload.objective == "maximize_comfort" and comfort_weight == 0.0:
        comfort_weight = 1.5

    def team_score_fn(members, slot_index: int):
        scored = score_team_composition(
            session, adapter, game_id, player.id, members,
            encounter_constraints=slot_constraints[slot_index],
            preferences=preferences,
            comfort_weight=comfort_weight,
        )
        scored_total = scored["total"]
        if payload.objective == "maximize_clears":
            # Once a slot is strong enough to likely clear, extra strength there
            # is worth nothing to this objective — push the surplus to weak slots.
            scored_total = min(scored_total, 7.0)
        return scored_total, scored["components"]

    result = optimize_team_allocation(
        roster, slot_count, team_size, team_score_fn,
        max_roster=min(len(roster), 15),
    )
    return {
        "encounter_key": payload.encounter_key,
        "objective": payload.objective,
        "feasible": result.feasible,
        "best": _allocation_dict(result.best) if result.best else None,
        "alternatives": [_allocation_dict(a) for a in result.alternatives],
        "greedy_comparison": _allocation_dict(result.greedy) if result.greedy else None,
        "explanation": result.explanation,
        "score_warning": (
            "All slot scores are labeled HEURISTIC components (synergy, encounter fit, "
            "build readiness, comfort). No DPS simulation exists; totals are relative "
            "only, and never percentages of real damage."
        ),
        "notes": [
            f"evaluated {result.evaluated_team_combos} team-slot combinations",
        ],
    }


def _allocation_dict(allocation) -> dict | None:
    if allocation is None:
        return None
    return {
        "total": allocation.total,
        "teams": allocation.teams,
    }


@router.post("/tutor/explain")
def tutor(game_id: str, payload: TutorRequest, request: Request, session: Session = Depends(get_db), player=Depends(resolve_player)):
    from game_companion.core.persona.store import PersonaStore

    adapter = adapter_for(game_id)
    store = PersonaStore(request.app.state.settings)
    persona = store.get(payload.persona_id) if payload.persona_id else store.get("companion")
    fragment = persona.system_prompt_fragment(
        terminology_line=(
            f"In this game, characters are called '{adapter.terminology().character}', "
            f"weapon-like equipment '{adapter.terminology().equipment}', and gear pieces "
            f"'{adapter.terminology().gear}'."
        )
    )
    return tutor_explain(
        session, adapter, game_id, player.id,
        character_key=payload.character,
        topic=payload.topic,
        mode=payload.mode,
        persona_fragment=fragment,
        llm=request.app.state.llm,
    )
