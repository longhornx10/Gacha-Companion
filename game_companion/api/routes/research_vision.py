"""Research (sources/claims/changes) and screenshot import routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from game_companion.api.deps import adapter_for, get_db, resolve_player
from game_companion.api.schemas.requests import (
    ClaimCreate,
    ImportCreate,
    ResearchQuery,
    RosterImportCreate,
    SourceSeed,
)
from game_companion.api.serialize import claim_dict, import_dict, source_dict
from game_companion.core.research.service import ResearchService, provider_from_settings
from game_companion.core.vision.service import ImportService
from game_companion.db.repositories import ImportRepository, ResearchRepository

router = APIRouter(prefix="/games/{game_id}")


def _service(session: Session, game_id: str) -> ResearchService:
    return ResearchService(session, adapter_for(game_id))


# -- sources -------------------------------------------------------------------


@router.get("/sources")
def list_sources(game_id: str, session: Session = Depends(get_db)):
    rows = ResearchRepository(session).list_all(game_id=game_id)
    return {"sources": [source_dict(s) for s in rows]}


@router.post("/sources", status_code=201)
def add_sources(game_id: str, payload: SourceSeed, session: Session = Depends(get_db)):
    service = _service(session, game_id)
    if payload.seed_defaults:
        seeded = service.seed_sources()
        return {"seeded": [source_dict(s) for s in seeded]}
    row = service.repo.upsert_source(
        game_id=game_id,
        key=payload.key or "",
        name=payload.name or "",
        url=payload.url or "",
        category=payload.category,
        trust=payload.trust,
        notes=payload.notes,
    )
    return source_dict(row)


# -- claims ---------------------------------------------------------------------


@router.get("/claims")
def list_claims(game_id: str, subject: str | None = None, claim_type: str | None = None, session: Session = Depends(get_db)):
    rows = ResearchRepository(session).claims(game_id, subject=subject, claim_type=claim_type)
    return {"claims": [claim_dict(c) for c in rows]}


@router.post("/claims", status_code=201)
def add_claim(game_id: str, payload: ClaimCreate, session: Session = Depends(get_db)):
    service = _service(session, game_id)
    claim = service.add_claim(
        subject=payload.subject,
        claim_type=payload.claim_type,
        content=payload.content,
        source_key=payload.source_key,
        confidence=payload.confidence,
        evidence=payload.evidence,
    )
    return claim_dict(claim)


@router.get("/claims/cross-check/{subject}")
def cross_check_claims(game_id: str, subject: str, session: Session = Depends(get_db)):
    return _service(session, game_id).cross_check(subject)


@router.post("/research/query")
def research_query(game_id: str, payload: ResearchQuery, request: Request, session: Session = Depends(get_db), player=Depends(resolve_player)):
    service = _service(session, game_id)
    provider = provider_from_settings(request.app.state.settings)
    llm = request.app.state.llm
    return service.query(question=payload.question, subject=payload.subject, provider=provider, llm=llm)


# -- change records (M19) ---------------------------------------------------------


@router.get("/changes")
def list_changes(game_id: str, review_status: str | None = None, session: Session = Depends(get_db)):
    rows = ResearchRepository(session).changes(game_id, review_status)
    return {
        "changes": [
            {
                "id": c.id,
                "entity_type": c.entity_type,
                "entity_key": c.entity_key,
                "detected_at": str(c.detected_at),
                "previous_value": c.previous_value,
                "proposed_value": c.proposed_value,
                "review_status": c.review_status,
                "confidence": c.confidence,
                "evidence": c.evidence,
            }
            for c in rows
        ]
    }


@router.post("/changes/check-sources")
def check_sources(game_id: str, session: Session = Depends(get_db)):
    return _service(session, game_id).check_sources()


@router.post("/changes/{change_id}/approve")
def approve_change(game_id: str, change_id: str, session: Session = Depends(get_db)):
    return _service(session, game_id).decide_change(change_id, approve=True)


@router.post("/changes/{change_id}/reject")
def reject_change(game_id: str, change_id: str, session: Session = Depends(get_db)):
    return _service(session, game_id).decide_change(change_id, approve=False)


# -- screenshot imports (M5) --------------------------------------------------------


@router.post("/imports")
def create_import(game_id: str, payload: ImportCreate, request: Request, session: Session = Depends(get_db), player=Depends(resolve_player)):
    service = ImportService(session, adapter_for(game_id))
    result = service.create_import(
        game_id,
        player.id,
        screen_type=payload.screen_type,
        candidate=payload.candidate,
        image_base64=payload.image_base64,
        screenshot_name=payload.screenshot_name,
        character_hint=payload.character_hint,
        llm=request.app.state.llm,
    )
    return result


@router.get("/imports")
def list_imports(game_id: str, session: Session = Depends(get_db), player=Depends(resolve_player)):
    rows = ImportRepository(session).list_all(game_id=game_id, player_profile_id=player.id)
    return {"imports": [import_dict(i) for i in rows]}


@router.post("/import-roster")
def import_roster(game_id: str, payload: RosterImportCreate, session: Session = Depends(get_db), player=Depends(resolve_player)):
    from game_companion.core.roster import importer

    adapter = adapter_for(game_id)
    if payload.text:
        parsed = importer.parse_roster_text(payload.text, adapter)
    elif payload.json_data is not None:
        parsed = importer.parse_roster_json(payload.json_data, adapter)
    else:
        from game_companion.errors import ValidationError

        raise ValidationError("provide 'text' (plain-text roster) or 'json_data'")
    row = importer.stage_roster_import(session, adapter, game_id, player.id, parsed)
    return importer.summarize(row)


@router.get("/imports/{import_id}")
def get_import(game_id: str, import_id: str, session: Session = Depends(get_db), player=Depends(resolve_player)):
    return import_dict(ImportRepository(session).get_or_raise(import_id, "import"))


@router.post("/imports/{import_id}/confirm")
def confirm_import(game_id: str, import_id: str, session: Session = Depends(get_db), player=Depends(resolve_player)):
    service = ImportService(session, adapter_for(game_id))
    return service.confirm(import_id)


@router.post("/imports/{import_id}/reject")
def reject_import(game_id: str, import_id: str, session: Session = Depends(get_db), player=Depends(resolve_player)):
    service = ImportService(session, adapter_for(game_id))
    return service.reject(import_id)


# -- reference catalog (M25) ----------------------------------------------------


@router.get("/catalog")
def list_catalog(game_id: str, entity_type: str | None = None, session: Session = Depends(get_db)):
    from game_companion.core.catalog.service import CatalogService

    service = CatalogService(session, adapter_for(game_id))
    entries = service.entries(entity_type)
    return {
        "entries": [
            {
                "entity_type": e.entity_type,
                "key": e.key,
                "display_name": e.display_name,
                "rarity": e.rarity,
                "meta": e.meta,
                "source": e.source,
                "updated_at": e.updated_at.isoformat() if e.updated_at else None,
            }
            for e in entries
        ],
        "runs": [
            {
                "source_key": r.source_key,
                "kind": r.kind,
                "status": r.status,
                "detail": r.detail,
                "items": r.items,
                "fetched_at": r.fetched_at.isoformat() if r.fetched_at else None,
            }
            for r in service.runs()
        ],
    }


@router.post("/catalog/refresh")
def refresh_catalog(
    game_id: str,
    request: Request,
    source_key: str = "auto",
    session: Session = Depends(get_db),
):
    from game_companion.core.catalog.service import CatalogService

    service = CatalogService(session, adapter_for(game_id))
    summary = service.refresh(
        source_key, transport=getattr(request.app.state, "llm_transport", None)
    )
    session.commit()
    return {"game_id": game_id, "summary": summary}
