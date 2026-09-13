"""Codes, combat history and training routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from game_companion.api.deps import adapter_for, get_db, resolve_player
from game_companion.api.schemas.requests import (
    CodeCreate,
    CodeUpdate,
    CombatResultCreate,
    TrainingGoalCreate,
    TrainingGoalUpdate,
    TrainingIssueCreate,
    TrainingIssueUpdate,
)
from game_companion.api.serialize import (
    code_dict,
    combat_result_dict,
    training_goal_dict,
    training_issue_dict,
)
from game_companion.core.coaching.training import TrainingService
from game_companion.core.codes.service import CodeService
from game_companion.core.history.service import CombatService
from game_companion.db.repositories import CodeRepository

router = APIRouter(prefix="/games/{game_id}")


# -- codes ----------------------------------------------------------------------


@router.get("/codes")
def list_codes(game_id: str, session: Session = Depends(get_db), player=Depends(resolve_player)):
    service = CodeService(session, adapter_for(game_id))
    out = []
    for code_row, state in service.list_codes(player.id):
        out.append(code_dict(code_row, state))
    return {"codes": out, "code_config": adapter_for(game_id).code_config()}


@router.post("/codes", status_code=201)
def add_code(game_id: str, payload: CodeCreate, session: Session = Depends(get_db), player=Depends(resolve_player)):
    service = CodeService(session, adapter_for(game_id))
    row = service.add_code(
        payload.code, status=payload.status, expires_at=payload.expires_at, notes=payload.notes
    )
    return code_dict(row, service.codes.player_state(row.id, player.id))


@router.patch("/codes/{code_id}")
def update_code(game_id: str, code_id: str, payload: CodeUpdate, session: Session = Depends(get_db), player=Depends(resolve_player)):
    from game_companion.errors import ValidationError

    repo = CodeRepository(session)
    row = repo.get_or_raise(code_id, "code")
    if payload.status is not None:
        if payload.status not in ("active", "expired", "unknown", "recycled"):
            raise ValidationError("status must be active|expired|unknown|recycled")
        row.status = payload.status
    if payload.notes is not None:
        row.notes = payload.notes
    if payload.expires_at is not None:
        parsed = None
        try:
            from datetime import datetime

            parsed = datetime.fromisoformat(payload.expires_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValidationError(f"invalid expires_at: {exc}") from exc
        row.expires_at = parsed
    service = CodeService(session, adapter_for(game_id))
    return code_dict(row, service.codes.player_state(row.id, player.id))


@router.post("/codes/{code_id}/mark-used")
def mark_code_used(game_id: str, code_id: str, session: Session = Depends(get_db), player=Depends(resolve_player)):
    service = CodeService(session, adapter_for(game_id))
    state = service.mark_used(code_id, player.id, True)
    return {"code_id": code_id, "used": state.used, "used_at": str(state.used_at)}


@router.post("/codes/{code_id}/mark-unused")
def mark_code_unused(game_id: str, code_id: str, session: Session = Depends(get_db), player=Depends(resolve_player)):
    service = CodeService(session, adapter_for(game_id))
    state = service.mark_used(code_id, player.id, False)
    return {"code_id": code_id, "used": state.used}


@router.get("/codes.md", response_class=Response)
def codes_markdown(game_id: str, session: Session = Depends(get_db), player=Depends(resolve_player)):
    service = CodeService(session, adapter_for(game_id))
    return Response(
        content=service.render_codes_markdown(player.id),
        media_type="text/markdown",
        headers={"Content-Disposition": "inline"},
    )


# -- combat history ---------------------------------------------------------------


@router.get("/combat-results")
def list_combat_results(
    game_id: str, encounter: str | None = None, session: Session = Depends(get_db), player=Depends(resolve_player)
):
    from game_companion.db.repositories import HistoryRepository

    rows = HistoryRepository(session).results(game_id, player.id, encounter)
    return {"results": [combat_result_dict(r) for r in rows]}


@router.post("/combat-results", status_code=201)
def record_combat_result(game_id: str, payload: CombatResultCreate, session: Session = Depends(get_db), player=Depends(resolve_player)):
    service = CombatService(session)
    row = service.record(game_id, player.id, payload.model_dump(exclude_unset=True))
    return combat_result_dict(row)


@router.get("/combat-results/trends")
def combat_trends(game_id: str, encounter: str | None = None, session: Session = Depends(get_db), player=Depends(resolve_player)):
    service = CombatService(session)
    return service.trends(game_id, player.id, encounter)


# -- training ----------------------------------------------------------------------


@router.get("/training/issues")
def list_training_issues(
    game_id: str, status: str | None = None, session: Session = Depends(get_db), player=Depends(resolve_player)
):
    from game_companion.db.repositories import TrainingRepository

    rows = TrainingRepository(session).issues(game_id, player.id, status)
    return {"issues": [training_issue_dict(i) for i in rows]}


@router.post("/training/issues", status_code=201)
def record_training_issue(game_id: str, payload: TrainingIssueCreate, session: Session = Depends(get_db), player=Depends(resolve_player)):
    service = TrainingService(session)
    outcome = service.record_issue(
        game_id, player.id, payload.category, payload.description,
        payload.character_keys, payload.severity, payload.notes,
    )
    from game_companion.db.repositories import TrainingRepository

    row = TrainingRepository(session).get(outcome["issue_id"])
    return {**outcome, "issue": training_issue_dict(row)}


@router.patch("/training/issues/{issue_id}")
def update_training_issue(game_id: str, issue_id: str, payload: TrainingIssueUpdate, session: Session = Depends(get_db), player=Depends(resolve_player)):
    service = TrainingService(session)
    row = service.update_issue(issue_id, payload.model_dump(exclude_unset=True))
    return training_issue_dict(row)


@router.get("/training/goals")
def list_training_goals(game_id: str, session: Session = Depends(get_db), player=Depends(resolve_player)):
    from game_companion.db.repositories import GoalRepository

    rows = GoalRepository(session).goals(game_id, player.id)
    return {"goals": [training_goal_dict(g) for g in rows]}


@router.post("/training/goals", status_code=201)
def add_training_goal(game_id: str, payload: TrainingGoalCreate, session: Session = Depends(get_db), player=Depends(resolve_player)):
    service = TrainingService(session)
    row = service.add_goal(game_id, player.id, payload.description, payload.target)
    return training_goal_dict(row)


@router.patch("/training/goals/{goal_id}")
def update_training_goal(game_id: str, goal_id: str, payload: TrainingGoalUpdate, session: Session = Depends(get_db), player=Depends(resolve_player)):
    service = TrainingService(session)
    row = service.update_goal(goal_id, payload.model_dump(exclude_unset=True))
    return training_goal_dict(row)


@router.get("/training/focus")
def training_focus(game_id: str, session: Session = Depends(get_db), player=Depends(resolve_player)):
    service = TrainingService(session)
    issues = service.open_issues(game_id, player.id)
    return {
        "focus": [
            {
                "category": i.category,
                "description": i.description,
                "occurrences": i.occurrences,
                "character_keys": i.character_keys,
                "severity": i.severity,
            }
            for i in issues
        ],
        "note": "recurring issues (same category + characters) bump occurrence counts",
    }
