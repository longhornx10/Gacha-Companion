"""Export routes: write regenerable JSON + Markdown exports."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from game_companion.api.deps import adapter_for, get_db, resolve_player, settings_dep
from game_companion.core.exports.service import ExportService

router = APIRouter(prefix="/games/{game_id}")


@router.post("/exports")
def write_exports(
    game_id: str,
    session: Session = Depends(get_db),
    player=Depends(resolve_player),
    settings=Depends(settings_dep),
):
    service = ExportService(session, adapter_for(game_id), settings)
    paths = service.write_exports(game_id, player.id)
    return {
        "written": [str(p) for p in paths],
        "note": "Exports are regenerable snapshots; SQLite remains the authoritative store.",
    }


@router.get("/export.json")
def export_json(
    game_id: str,
    session: Session = Depends(get_db),
    player=Depends(resolve_player),
    settings=Depends(settings_dep),
):
    service = ExportService(session, adapter_for(game_id), settings)
    import json

    return Response(
        content=json.dumps(service.collect(game_id, player.id), indent=2, ensure_ascii=False, default=str),
        media_type="application/json",
    )
