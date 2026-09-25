"""``/ui`` page routes — server-rendered, zero business logic.

Every page resolves the UI context (active player + active game) and renders
read views over existing services. Forms post back here and redirect; the JSON
API under /api remains the programmatic surface.
"""

from __future__ import annotations

import base64
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from game_companion.api.deps import adapter_for, get_db
from game_companion.config import Settings
from game_companion.core import dashboard as dashboard_mod
from game_companion.core.backup import cleanup_staging, create_backup, list_backups, stage_restore
from game_companion.core.catalog.service import CatalogService
from game_companion.core.codes.service import CodeService
from game_companion.core.games.registry import list_adapters
from game_companion.core.recommendations.planner import audit_roster
from game_companion.core.resources.service import ResourceService
from game_companion.core.roster.service import RosterService
from game_companion.core.teams.service import TeamService
from game_companion.db.backup_swap import swap_live_database
from game_companion.db.models import CompanionMemory, PlayerProfile
from game_companion.db.repositories import (
    CharacterRepository,
    EquipmentRepository,
    GearRepository,
    HistoryRepository,
    ImportRepository,
    PlayerRepository,
    ResourceRepository,
    TeamRepository,
)
from game_companion.ui import state as ui_state
from game_companion.utils import to_iso

router = APIRouter(prefix="/ui", include_in_schema=False)

_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
_STATIC_DIR = Path(__file__).resolve().parent / "static"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
templates.env.filters["isodate"] = to_iso
templates.env.filters["catplural"] = lambda kind: {
    "character": "characters", "equipment": "equipment", "gear_set": "gear sets",
    "codes": "codes",
}.get(kind, kind)

STATUS_CHIP = {
    "critically_low": "chip-red",
    "very_low": "chip-orange",
    "done": "chip-white",
    "prep": "chip-cyan",
    "unknown": "chip-gray",
}


def _ctx(request: Request, session: Session, title: str, active: str, **extra):
    settings: Settings = request.app.state.settings
    context = ui_state.resolve_context(settings, session)
    games = [
        {"game_id": a.game_id, "display_name": a.display_name, "theme": a.theme()}
        for a in list_adapters()
    ]
    adapter = adapter_for(context.active_game)
    term = adapter.terminology()
    notice = request.query_params.get("notice") or ""
    return templates.TemplateResponse(
        request,
        name=extra.pop("template"),
        context={
            "title": title,
            "active": active,
            "ctx": context,
            "games": games,
            "theme": adapter.theme(),
            "term": term,
            "term_plural": {
                "character": term.character_plural,
                "equipment": term.equipment_plural,
                "gear": term.gear_plural,
            },
            "game_id": context.active_game,
            "player_id": context.player.id if context.player else None,
            "notice": notice,
            **extra,
        },
    )


def _page(template: str, title: str, active: str):
    def _render(request: Request, session: Session = Depends(get_db)):
        return _ctx(request, session, title, active, template=template)

    return _render


def _home_banners(session: Session, adapter) -> dict:
    """Live + upcoming banners for the Home rail, from catalog rows.

    Honest windows: a banner only counts as live when both dates parse and
    now falls inside them; anything undated is simply not shown.
    """
    from datetime import datetime as _dt

    from game_companion.core.catalog.service import CatalogService
    from game_companion.utils import utcnow

    def _parse(value):
        if not value:
            return None
        try:
            parsed = _dt.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:  # offset-less format: treat as UTC
            parsed = parsed.replace(tzinfo=_dt.timezone.utc)
        return parsed

    live: list[dict] = []
    upcoming: list[dict] = []
    now = utcnow()
    for e in CatalogService(session, adapter).entries("banner"):
        m = dict(e.meta or {})
        start, end = _parse(m.get("starts_at")), _parse(m.get("ends_at"))
        row = {
            "name": e.display_name,
            "kind": m.get("kind"),
            "banner_type": m.get("banner_type"),
            "art": m.get("art"),
            "phase": m.get("phase"),
            "featured": [
                f.get("name") for f in (m.get("featured") or []) if f.get("name")
            ],
            "ends_label": f"Ends {end.strftime('%b %d')}" if end else None,
            "starts_label": f"from {start.strftime('%b %d')}" if start else None,
        }
        if start and end and start <= now <= end:
            live.append(row)
        elif start and start > now:
            upcoming.append(row)
    live.sort(key=lambda r: (r["ends_label"] or "zzz", r["name"]))
    upcoming.sort(key=lambda r: r["starts_label"] or "zzz")
    # hero prefers the patch's new character banner over reruns of the same window
    ranked = sorted(
        (r for r in live if r["kind"] != "weapon"),
        key=lambda r: (0 if r["banner_type"] == "new" else 1, r["ends_label"] or "zzz", r["name"]),
    )
    hero = ranked[0] if ranked else (live[0] if live else None)
    also = [
        {"name": r["name"], "banner_type": r["banner_type"]}
        for r in live if r is not hero
    ][:3]
    return {
        "hero": hero,
        "also": also,
        "next": upcoming[0] if upcoming else None,
    }


@router.get("", response_class=HTMLResponse)
def home(request: Request, c: str = "", session: Session = Depends(get_db)):
    settings = request.app.state.settings
    context = ui_state.resolve_context(settings, session)
    if context.needs_setup:
        return _ctx(request, session, "Welcome", "dashboard", template="setup.html")
    adapter = adapter_for(context.active_game)
    data = dashboard_mod.build_dashboard(session, adapter, context.player.id)
    for r in data["resources"]:
        r["chip"] = STATUS_CHIP.get(r.get("status"), "chip-gray")

    # chat is the primary interactor and lives on Home
    from game_companion.core.persona.store import PersonaStore

    _, chat = _chat_service(request, session)
    conversations = chat.list_conversations()
    conv = None
    if c:
        try:
            conv = chat.get_conversation(c)
        except Exception:
            return _redirect("/ui")
    personas = [
        p
        for p in PersonaStore(settings).list_personas()
        if p.bound_game in (None, context.active_game)
    ]
    messages = []
    if conv:
        for m in conv.messages:
            entry = {"role": m.role, "content": m.content, "tool_name": m.tool_name}
            if m.role == "assistant" and m.tool_calls:
                entry["tools"] = [
                    call.get("function", {}).get("name", "tool")
                    for call in m.tool_calls
                    if isinstance(call, dict)
                ]
            messages.append(entry)

    # rail widgets: fresh achievement states + current banner (community data)
    from game_companion.core.achievements.service import check_and_unlock

    achievements, _ = check_and_unlock(session, adapter, context.player.id)
    session.commit()
    banners = _home_banners(session, adapter)

    return _ctx(
        request,
        session,
        "Home",
        "dashboard",
        template="dashboard.html",
        dashboard=data,
        conversations=conversations,
        current=conv,
        chat_messages=messages,
        personas=personas,
        current_game=context.active_game,
        achievements=achievements,
        banners=banners,
    )


@router.get("/hall", response_class=HTMLResponse)
def hall(request: Request, session: Session = Depends(get_db)):
    """The Hall: the collection page — your team, your people, their gear."""
    settings = request.app.state.settings
    context = ui_state.resolve_context(settings, session)
    if context.needs_setup:
        return _ctx(request, session, "Welcome", "dashboard", template="setup.html")
    adapter = adapter_for(context.active_game)
    game_id, player_id = context.active_game, context.player.id

    chars = CharacterRepository(session).search(game_id, player_id)
    owned = [c for c in chars if c.owned]
    gear = GearRepository(session).search(game_id, player_id)
    equipment = EquipmentRepository(session).search(game_id, player_id)
    discs_by_char: dict[str, list] = {}
    for g in gear:
        if g.equipped_character_id and g.set_key:
            discs_by_char.setdefault(g.equipped_character_id, []).append(g)
    engine_by_char = {
        e.equipped_character_id: e for e in equipment if e.equipped_character_id
    }

    def card(c) -> dict:
        element = (c.data or {}).get("attribute")
        d = sorted(discs_by_char.get(c.id, []), key=lambda g: g.slot or "")
        return {
            "key": c.key,
            "name": c.display_name,
            "rarity": c.rarity,
            "level": c.level,
            "dupe": c.duplication_level,
            "favorite": c.favorite,
            "portrait": adapter.media_url("character", c.key),
            "element": element,
            "element_icon": adapter.media_url("element", element) if element else None,
            "specialty": (c.data or {}).get("specialty"),
            "engine_icon": adapter.media_url("equipment", engine_by_char[c.id].key)
            if c.id in engine_by_char else None,
            "engine_name": engine_by_char[c.id].display_name if c.id in engine_by_char else None,
            "disc_icons": [adapter.media_url("gear_set", g.set_key) for g in d],
            "disc_slots": len(d),
            "edit": f"/ui/roster/{c.key}/edit",
        }

    cards = [card(c) for c in owned]
    cards.sort(key=lambda x: (-(x["rarity"] or 0), x["name"].lower()))

    teams = TeamRepository(session).list_all(game_id=game_id, player_profile_id=player_id)
    active_team = next((t for t in teams if t.is_active), None)
    by_key = {c.id: c for c in chars}
    team_cards = []
    if active_team:
        for m in sorted(active_team.members, key=lambda m: m.position):
            ch = by_key.get(m.character_id)
            if ch is not None and ch.owned:
                team_cards.append(card(ch))

    # latest catalog additions — "what's new in the game", honestly labeled
    from game_companion.core.catalog.service import CatalogService

    catalog = CatalogService(session, adapter)
    latest = sorted(
        (e for e in catalog.entries("character") if "{" not in e.display_name),
        key=lambda e: (e.created_at, e.display_name),
        reverse=True,
    )[:6]
    latest_cards = [
        {
            "name": e.display_name,
            "rarity": e.rarity,
            "portrait": adapter.media_url("character", e.key),
        }
        for e in latest
    ]

    from game_companion.core.achievements.service import check_and_unlock

    achievements, newly = check_and_unlock(session, adapter, player_id)
    session.commit()

    return _ctx(
        request,
        session,
        "The Hall",
        "hall",
        template="hall.html",
        cards=cards,
        team_cards=team_cards,
        latest_cards=latest_cards,
        achievements=achievements,
        newly_unlocked=newly,
        char_term=adapter.terminology().character,
        char_term_plural=adapter.terminology().character_plural,
        mood=adapter.theme().get("mood"),
    )


@router.get("/roster", response_class=HTMLResponse)
def roster(request: Request, session: Session = Depends(get_db)):
    settings = request.app.state.settings
    context = ui_state.resolve_context(settings, session)
    if context.needs_setup:
        return RedirectResponse("/ui", status_code=303)
    adapter = adapter_for(context.active_game)
    chars = CharacterRepository(session).search(context.active_game, context.player.id)
    from game_companion.api.serialize import character_dict

    catalog = CatalogService(session, adapter).entries("character")
    owned = {c.key for c in chars}
    return _ctx(
        request,
        session,
        adapter.terminology().character_plural,
        "roster",
        template="roster.html",
        characters=[character_dict(c) for c in chars],
        catalog=[
            {
                "key": e.key,
                "display_name": e.display_name,
                "rarity": e.rarity,
                "owned": e.key in owned,
            }
            for e in catalog
        ],
    )


@router.post("/roster/add")
def roster_add(
    request: Request,
    catalog_key: str = Form(...),
    level: str = Form(""),
    duplication_level: str = Form(""),
    session: Session = Depends(get_db),
):
    """Add an agent picked from the reference catalog — no manual keys."""
    context = ui_state.resolve_context(request.app.state.settings, session)
    if context.needs_setup:
        return _redirect("/ui")
    adapter = adapter_for(context.active_game)
    entry = CatalogService(session, adapter).find("character", catalog_key)
    if entry is None:
        return _redirect("/ui/roster", "Pick a name from the list — import the catalog on the Database page if it is empty")
    service = RosterService(session, adapter)
    try:
        choices = adapter.character_field_choices()
        data = {k: v for k, v in (entry.meta or {}).items() if k in choices and v}
        char = service.create_character(
            context.active_game, context.player.id,
            {"key": entry.key, "display_name": entry.display_name, "data": data},
        )
        patch: dict = {"owned": True, "source": "catalog"}
        if entry.rarity is not None:
            patch["rarity"] = str(entry.rarity)
        if level.strip():
            patch["level"] = int(level)
        if duplication_level.strip():
            patch["duplication_level"] = int(duplication_level)
        service.update_character(char, patch)
        session.commit()
    except Exception as exc:
        session.rollback()
        return _redirect("/ui/roster", f"Could not add: {exc}")
    return _redirect("/ui/roster", f"{entry.display_name} added")


@router.get("/teams", response_class=HTMLResponse)
def teams(request: Request, session: Session = Depends(get_db)):
    settings = request.app.state.settings
    context = ui_state.resolve_context(settings, session)
    if context.needs_setup:
        return RedirectResponse("/ui", status_code=303)
    adapter = adapter_for(context.active_game)
    rows = TeamRepository(session).list_all(
        game_id=context.active_game, player_profile_id=context.player.id
    )
    by_id = {c.id: c for c in CharacterRepository(session).search(context.active_game, context.player.id)}
    teams_out = []
    for t in rows:
        members = [
            {"position": m.position, "name": by_id[m.character_id].display_name if m.character_id in by_id else "?"}
            for m in t.members
        ]
        teams_out.append({"id": t.id, "name": t.name, "is_active": t.is_active, "notes": t.notes, "members": members})
    return _ctx(
        request, session, adapter.terminology().team + "s", "teams", template="teams.html", teams=teams_out
    )


@router.get("/gear", response_class=HTMLResponse)
def gear(request: Request, session: Session = Depends(get_db)):
    settings = request.app.state.settings
    context = ui_state.resolve_context(settings, session)
    if context.needs_setup:
        return RedirectResponse("/ui", status_code=303)
    adapter = adapter_for(context.active_game)
    characters = {
        c.id: c.display_name
        for c in CharacterRepository(session).search(context.active_game, context.player.id)
    }
    equipment = EquipmentRepository(session).search(context.active_game, context.player.id)
    gear_rows = GearRepository(session).search(context.active_game, context.player.id)
    catalog_service = CatalogService(session, adapter)
    set_choices: dict[str, str] = {}
    for s in adapter.gear_sets():
        if isinstance(s, dict) and s.get("key"):
            set_choices[s["key"]] = s.get("name") or s["key"]
    for e in catalog_service.entries("gear_set"):
        set_choices.setdefault(e.key, e.display_name)
    return _ctx(
        request,
        session,
        "Inventory",
        "gear",
        template="gear.html",
        equipment=[
            {
                "display_name": e.display_name,
                "rarity": e.rarity,
                "level": e.level,
                "refinement": e.refinement,
                "equipped": characters.get(e.equipped_character_id, ""),
                "locked": e.locked,
            }
            for e in equipment
        ],
        gear=[
            {
                "set_key": g.set_key,
                "slot": g.slot,
                "rarity": g.rarity,
                "level": g.level,
                "main": (
                    f"{g.main_stat_key} {g.main_stat_value:g}"
                    if g.main_stat_key and g.main_stat_value is not None
                    else (g.main_stat_key or "")
                ),
                "substats": len(g.substats or []),
                "equipped": characters.get(g.equipped_character_id, ""),
                "locked": g.locked,
                "favorite": g.favorite,
            }
            for g in gear_rows
        ],
        equipment_noun=adapter.terminology().equipment,
        gear_noun=adapter.terminology().gear,
        catalog_equipment=[
            {"key": e.key, "display_name": e.display_name, "rarity": e.rarity}
            for e in catalog_service.entries("equipment")
        ],
        set_choices=sorted(set_choices.items()),
        character_options=sorted(characters.items()),
        gear_slots=[
            {"key": s.key, "name": s.name} for s in adapter.gear_slots()
        ],
        stat_options=[{"key": s.key, "name": s.short or s.name} for s in adapter.stat_definitions()],
    )


# Friendly planner controls, mapped to the math behind the scenes.
SPARE_BETA = {"low": 1.0, "comfortable": 1.2, "lots": 1.5}
SPARE_LABELS = {
    "low": "Just what I need",
    "comfortable": "A comfortable margin",
    "lots": "Lots of spares",
}


def _coverage_word(coverage: float | None) -> str:
    c = 0.0 if coverage is None else coverage
    if c >= 1.0:
        return "covered"
    if c <= 0.0:
        return "none yet"
    if c < 0.34:
        return "a good start"
    if c < 0.67:
        return "getting there"
    return "almost there"


@router.get("/farm", response_class=HTMLResponse)
def farm_plan_page(
    request: Request,
    scope: str = "mine",
    spare: str = "comfortable",
    session: Session = Depends(get_db),
):
    settings = request.app.state.settings
    context = ui_state.resolve_context(settings, session)
    if context.needs_setup:
        return RedirectResponse("/ui", status_code=303)
    adapter = adapter_for(context.active_game)
    scope = scope if scope in ("mine", "meta") else "mine"
    spare = spare if spare in SPARE_BETA else "comfortable"
    beta = SPARE_BETA[spare]

    owned_keys = [
        c.key for c in CharacterRepository(session).search(context.active_game, context.player.id)
    ]
    rows = GearRepository(session).search(context.active_game, context.player.id)
    plan_rows = [
        {
            "gear_type": g.gear_type,
            "set_key": g.set_key,
            "slot": g.slot,
            "rarity": g.rarity,
            "level": g.level,
            "main_stat_key": g.main_stat_key,
            "equipped_character_id": g.equipped_character_id,
        }
        for g in rows
    ]
    unit_keys = owned_keys if scope == "mine" else None
    plan = adapter.build_farm_plan(plan_rows, beta=beta, unit_keys=unit_keys)

    simple: dict = {}
    if plan:
        stage_rows = plan.get("stage_rows") or []
        top_stage = stage_rows[0] if stage_rows else None
        sets = []
        for r in plan["set_rows"]:
            if r["target"] <= 0 or r["pressure"] <= 0:
                continue
            stage_name = None
            if r["farmable"] and r["farm_stage"]:
                stage_name = next(
                    (
                        s["name"]
                        for s in plan.get("stage_index") or []
                        if s["key"] == r["farm_stage"]
                    ),
                    r["farm_stage"],
                )
            sets.append({
                "name": r["set_name"],
                "word": _coverage_word(r["coverage"]),
                "pct": 0 if r["coverage"] is None else round(r["coverage"] * 100),
                "stage_name": stage_name,
                "farmable": r["farmable"],
                "pressure": r["pressure"],
            })
        sets.sort(key=lambda s: -s["pressure"])
        top_set = sets[0] if sets else None

        # verdict card copy: explain the chosen stage, and point at the single
        # biggest set gap when it lives somewhere else (granny-coherent)
        why = None
        gap_elsewhere = None
        if top_stage:
            gap_name = top_stage.get("bottleneck_set_name")
            gap_row = next(
                (r for r in plan["set_rows"] if r["set_name"] == gap_name), None
            )
            if gap_name:
                why = (
                    f"Drops {gap_name}, the set you need most here "
                    f"(currently: {_coverage_word(gap_row['coverage']) if gap_row else 'none yet'})."
                )
            if top_set and top_set.get("stage_name") and (
                not top_stage or top_set["stage_name"] != top_stage.get("stage_name")
            ):
                gap_elsewhere = (
                    f"Your biggest single gap is {top_set['name']} "
                    f"({top_set['word']}) — that one's at {top_set['stage_name']}."
                )

        simple = {
            "top_stage": top_stage,
            "other_stages": stage_rows[1:5],
            "top_set": top_set,
            "why": why,
            "gap_elsewhere": gap_elsewhere,
            "sets": sets[:8],
        }

    provenance = (plan or {}).get("provenance") or {}
    meta_src = provenance.get("meta") or {}
    return _ctx(
        request,
        session,
        "Farm Plan",
        "farm",
        template="farm.html",
        plan=plan,
        simple=simple,
        scope=scope,
        spare=spare,
        spare_labels=SPARE_LABELS,
        gear_noun=adapter.terminology().gear,
        gear_plural=adapter.terminology().gear_plural,
        meta_source=meta_src.get("source"),
        meta_patch=meta_src.get("patch"),
        meta_retrieved=meta_src.get("retrieved"),
    )


@router.post("/gear/equipment/add")
def gear_equipment_add(
    request: Request,
    catalog_key: str = Form(...),
    level: str = Form(""),
    refinement: str = Form(""),
    equipped_character_id: str = Form(""),
    session: Session = Depends(get_db),
):
    """Record an owned piece of equipment picked from the catalog."""
    context = ui_state.resolve_context(request.app.state.settings, session)
    if context.needs_setup:
        return _redirect("/ui")
    adapter = adapter_for(context.active_game)
    entry = CatalogService(session, adapter).find("equipment", catalog_key)
    if entry is None:
        return _redirect("/ui/gear", "Pick an item from the list — import the catalog on the Database page if it is empty")
    from game_companion.db.models import EquipmentItem
    from game_companion.utils import utcnow

    try:
        EquipmentRepository(session).add(
            EquipmentItem(
                game_id=context.active_game,
                player_profile_id=context.player.id,
                key=entry.key,
                display_name=entry.display_name,
                rarity=entry.rarity,
                level=int(level) if level.strip() else None,
                refinement=int(refinement) if refinement.strip() else None,
                equipped_character_id=equipped_character_id or None,
                source="catalog",
                last_verified_at=utcnow(),
            )
        )
        session.commit()
    except Exception as exc:
        session.rollback()
        return _redirect("/ui/gear", f"Could not add: {exc}")
    return _redirect("/ui/gear", f"{entry.display_name} added")


@router.post("/gear/gear/add")
def gear_gear_add(
    request: Request,
    set_key: str = Form(...),
    slot: str = Form(...),
    rarity: str = Form(""),
    level: str = Form(""),
    main_stat_key: str = Form(""),
    main_stat_value: str = Form(""),
    equipped_character_id: str = Form(""),
    session: Session = Depends(get_db),
):
    """Record one owned gear piece (disc/relic/cartridge) with its rolled stats."""
    context = ui_state.resolve_context(request.app.state.settings, session)
    if context.needs_setup:
        return _redirect("/ui")
    adapter = adapter_for(context.active_game)
    valid_slots = {s.key for s in adapter.gear_slots()}
    if slot not in valid_slots:
        return _redirect("/ui/gear", "Pick a slot from the list")
    from game_companion.db.models import GearItem
    from game_companion.utils import utcnow

    try:
        GearRepository(session).add(
            GearItem(
                game_id=context.active_game,
                player_profile_id=context.player.id,
                set_key=set_key,
                slot=slot,
                gear_type=adapter.gear_families()[0].key if adapter.gear_families() else "gear",
                rarity=int(rarity) if rarity.strip() else None,
                level=int(level) if level.strip() else None,
                main_stat_key=main_stat_key or None,
                main_stat_value=float(main_stat_value) if main_stat_value.strip() else None,
                equipped_character_id=equipped_character_id or None,
                source="manual",
                last_verified_at=utcnow(),
            )
        )
        session.commit()
    except Exception as exc:
        session.rollback()
        return _redirect("/ui/gear", f"Could not add: {exc}")
    return _redirect("/ui/gear", "Piece added")


@router.get("/trackers", response_class=HTMLResponse)
def trackers(request: Request, session: Session = Depends(get_db)):
    settings = request.app.state.settings
    context = ui_state.resolve_context(settings, session)
    if context.needs_setup:
        return RedirectResponse("/ui", status_code=303)
    adapter = adapter_for(context.active_game)
    rows = ResourceService(session, adapter).list_with_status(context.active_game, context.player.id)
    for r in rows:
        r["chip"] = STATUS_CHIP.get(r.get("status"), "chip-gray")
    pairs = CodeService(session, adapter).list_codes(context.player.id)
    codes = [
        {
            "id": c.id,
            "code": c.code,
            "status": c.status,
            "recycled": c.status == "recycled",
            "expires_at": to_iso(c.expires_at),
            "used": bool(s and s.used),
            "notes": c.notes,
        }
        for c, s in pairs
    ]
    source = adapter.codes_source()
    run = None
    if source:
        found = CatalogService(session, adapter).run_for(source["key"])
        if found:
            run = {
                "status": found.status,
                "detail": found.detail,
                "items": found.items,
                "fetched_at": to_iso(found.fetched_at)[:16].replace("T", " ") if found.fetched_at else None,
            }
    results = [
        {
            "encounter_key": r.encounter_key,
            "played_at": to_iso(r.played_at),
            "cleared": r.cleared,
            "stars": r.stars,
            "score": r.score,
            "rank": r.rank,
            "team": ", ".join(
                m.get("display_name", "") for m in (r.team_snapshot or {}).get("members", [])
            ),
        }
        for r in HistoryRepository(session).results(context.active_game, context.player.id)
    ]
    return _ctx(
        request,
        session,
        "Trackers",
        "trackers",
        template="trackers.html",
        resources=rows,
        codes=codes,
        codes_source=source,
        codes_run=run,
        results=results,
    )


@router.get("/resources", response_class=HTMLResponse)
def resources(request: Request, session: Session = Depends(get_db)):
    """Resources moved to Trackers."""
    if ui_state.resolve_context(request.app.state.settings, session).needs_setup:
        return RedirectResponse("/ui", status_code=303)
    return _redirect("/ui/trackers#resources", request.query_params.get("notice"))


@router.get("/codes", response_class=HTMLResponse)
def codes(request: Request, session: Session = Depends(get_db)):
    """Codes moved to Trackers."""
    if ui_state.resolve_context(request.app.state.settings, session).needs_setup:
        return RedirectResponse("/ui", status_code=303)
    return _redirect("/ui/trackers#codes", request.query_params.get("notice"))


@router.post("/codes/refresh")
def codes_refresh(request: Request, session: Session = Depends(get_db)):
    """Pull the latest codes from the game's auto source, right now."""
    context = ui_state.resolve_context(request.app.state.settings, session)
    if context.needs_setup:
        return _redirect("/ui")
    service = CodeService(session, adapter_for(context.active_game))
    try:
        summary = service.refresh_from_source(
            transport=getattr(request.app.state, "llm_transport", None)
        )
        session.commit()
    except Exception as exc:
        session.rollback()
        return _redirect("/ui/trackers#codes", f"Refresh failed: {exc}")
    if summary["status"] != "ok":
        return _redirect("/ui/trackers#codes", f"Source unavailable: {summary.get('detail', 'unknown reason')} — it will retry automatically")
    return _redirect("/ui/trackers#codes", f"Codes refreshed from {summary.get('source', 'source')} ({summary['items']} known, {summary['added']} new)")


@router.get("/history", response_class=HTMLResponse)
def history(request: Request, session: Session = Depends(get_db)):
    """Combat history moved to Trackers."""
    if ui_state.resolve_context(request.app.state.settings, session).needs_setup:
        return RedirectResponse("/ui", status_code=303)
    return _redirect("/ui/trackers#history", request.query_params.get("notice"))


@router.get("/audit", response_class=HTMLResponse)
def audit(request: Request, session: Session = Depends(get_db)):
    settings = request.app.state.settings
    context = ui_state.resolve_context(settings, session)
    if context.needs_setup:
        return RedirectResponse("/ui", status_code=303)
    adapter = adapter_for(context.active_game)
    outcome = audit_roster(session, adapter, context.active_game, context.player.id, None)
    return _ctx(request, session, "Roster audit", "roster", template="audit.html", audit=outcome)


@router.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request, session: Session = Depends(get_db)):
    settings = request.app.state.settings
    context = ui_state.resolve_context(settings, session)
    games = [
        {"game_id": a.game_id, "display_name": a.display_name, "version": a.version}
        for a in list_adapters()
    ]
    memories = []
    if context.player:
        from game_companion.core.chat.service import ChatService

        chat_service = ChatService(session, adapter_for(context.active_game), context.player.id, None)
        memories = chat_service.memories(include_inactive=True)
    llm = request.app.state.llm
    llm_status = {
        "configured": getattr(llm, "configured", False),
        "base_url": getattr(llm, "base_url", ""),
        "model": getattr(llm, "model", ""),
        "vision_capable": getattr(llm, "vision_capable", True),
        "key_set": bool(settings.llm_api_key_plain()),
        "timeout_seconds": settings.llm_timeout_seconds,
        "searxng_base_url": settings.searxng_base_url or "",
        "vision_override": settings.llm_vision_model,
    }
    return _ctx(
        request,
        session,
        "Settings",
        "settings",
        template="settings.html",
        players=context.players,
        games=games,
        data_dir=str(settings.resolved_data_dir),
        backups=list_backups(settings),
        memories=memories,
        llm=llm_status,
    )


@router.post("/settings/assistant")
async def settings_assistant(request: Request, session: Session = Depends(get_db)):
    """Save Assistant-model settings to .env and hot-apply them (no restart)."""
    from game_companion.api.routes.llm import LlmConfigUpdate, _apply_llm_config

    form = await request.form()

    def field(name: str):
        value = form.get(name)
        return str(value).strip() if value is not None else None

    try:
        payload = LlmConfigUpdate(
            llm_base_url=field("llm_base_url") or None,
            llm_api_key=field("llm_api_key") or None,  # empty = keep saved key
            llm_model=field("llm_model") or None,
            llm_timeout_seconds=float(field("llm_timeout_seconds")) if field("llm_timeout_seconds") else None,
            vision_override=field("vision_override") or None,
            searxng_base_url=field("searxng_base_url"),
        )
        if not any([
            payload.llm_base_url, payload.llm_api_key, payload.llm_model,
            payload.llm_timeout_seconds is not None,
            payload.vision_override, payload.searxng_base_url is not None,
        ]):
            return _redirect("/ui/settings", "Nothing to change")
        _apply_llm_config(request.app, _changes_from_payload(payload))
    except Exception as exc:
        return _redirect("/ui/settings", f"Could not save assistant settings: {exc}")
    return _redirect("/ui/settings", "Assistant model saved and applied live")


def _changes_from_payload(payload):
    changes: dict = {}
    if payload.llm_base_url is not None:
        changes["llm_base_url"] = payload.llm_base_url
    if payload.llm_api_key is not None:
        changes["llm_api_key"] = payload.llm_api_key
    if payload.llm_model is not None:
        changes["llm_model"] = payload.llm_model
    if payload.llm_timeout_seconds is not None:
        changes["llm_timeout_seconds"] = payload.llm_timeout_seconds
    if payload.vision_override is not None:
        changes["llm_vision_model"] = (
            "" if payload.vision_override == "auto"
            else ("true" if payload.vision_override == "yes" else "false")
        )
    if payload.searxng_base_url is not None:
        changes["searxng_base_url"] = payload.searxng_base_url
    return changes


# -- form actions -----------------------------------------------------------------


def _redirect(path: str, notice: str | None = None) -> RedirectResponse:
    from urllib.parse import quote

    if notice:
        # keep any #fragment at the very end of the Location URL
        fragment = ""
        base = path
        if "#" in path:
            base, fragment = path.split("#", 1)
            fragment = f"#{fragment}"
        sep = "&" if "?" in base else "?"
        path = f"{base}{sep}notice={quote(notice)}{fragment}"
    return RedirectResponse(path, status_code=303)


def _safe_next(raw: str | None) -> str:
    return raw if raw and raw.startswith("/ui") else "/ui"


@router.post("/select-game")
def select_game(request: Request, game_id: str = Form(...), next: str = Form("/ui"), session: Session = Depends(get_db)):
    settings = request.app.state.settings
    try:
        ui_state.select_game(settings, session, game_id)
    except Exception:
        return _redirect(_safe_next(next), "Unknown game")
    session.commit()
    return _redirect(_safe_next(next), f"Switched to {adapter_for(game_id).display_name}")


@router.post("/select-player")
def select_player(request: Request, player_id: str = Form(...), next: str = Form("/ui"), session: Session = Depends(get_db)):
    settings = request.app.state.settings
    try:
        ui_state.select_player(settings, session, player_id)
    except Exception:
        return _redirect(_safe_next(next), "Unknown player")
    session.commit()
    return _redirect(_safe_next(next))


@router.post("/players/create")
def create_player_ui(request: Request, display_name: str = Form(...), session: Session = Depends(get_db)):
    settings = request.app.state.settings
    name = display_name.strip() or "Player"
    profile = PlayerRepository(session).add(PlayerProfile(display_name=name))
    session.commit()
    ui_state.select_player(settings, session, profile.id)
    return _redirect("/ui", f"Welcome, {name}!")


@router.post("/backup")
def backup_ui(request: Request):
    path = create_backup(request.app.state.settings)
    return _redirect("/ui/settings", f"Backup created: {path.name}")


@router.post("/restore")
def restore_ui(request: Request, name: str = Form(...), session: Session = Depends(get_db)):
    settings = request.app.state.settings
    session.rollback()
    try:
        staging, staged_db = stage_restore(settings, name)
    except Exception as exc:
        return _redirect("/ui/settings", f"Restore failed: {exc}")
    swap_live_database(request.app, staged_db, staging)
    cleanup_staging(settings)
    return _redirect("/ui", f"Restored from {name}")


# -- imports (M21) ------------------------------------------------------------------


def _needs_setup_redirect(request: Request, session: Session):
    settings = request.app.state.settings
    context = ui_state.resolve_context(settings, session)
    if context.needs_setup:
        return RedirectResponse("/ui", status_code=303)
    return None


@router.get("/imports", response_class=HTMLResponse)
def imports_page(request: Request, session: Session = Depends(get_db)):
    early = _needs_setup_redirect(request, session)
    if early:
        return early
    settings = request.app.state.settings
    context = ui_state.resolve_context(settings, session)
    adapter = adapter_for(context.active_game)
    rows = ImportRepository(session).list_all(
        game_id=context.active_game, player_profile_id=context.player.id
    )
    imports_out = []
    for row in rows:
        diff = row.diff or {}
        imports_out.append(
            {
                "id": row.id,
                "screen_type": row.screen_type,
                "status": row.status,
                "name": row.screenshot_name or row.id[:8],
                "changes": diff.get("changes", []),
                "unresolved": diff.get("unresolved", []),
                "error": row.error,
                "created_at": to_iso(row.created_at),
            }
        )
    families = [f.display for f in adapter.gear_families()] or None
    llm = request.app.state.llm
    vision_warning = None
    if not getattr(llm, "configured", False):
        vision_warning = "No model configured yet — set it in Settings → Assistant model."
    elif not getattr(llm, "vision_capable", True):
        # the name looks non-vision, but brokers with "auto" routing may still
        # accept images — the real test happens on upload now
        vision_warning = (
            f"Model '{llm.model}' doesn't advertise vision — we'll auto-test it when you "
            "upload, and Settings → Assistant model has a vision override."
        )
    return _ctx(
        request,
        session,
        "Imports",
        "imports",
        template="imports.html",
        imports=imports_out,
        screen_types=sorted(adapter.screenshot_specs()),
        gear_family_note=families[0] if families else adapter.terminology().gear,
        vision_warning=vision_warning,
        model_name=getattr(llm, "model", ""),
    )


@router.post("/imports/roster-txt")
def imports_roster_txt(request: Request, text: str = Form(...), session: Session = Depends(get_db)):
    early = _needs_setup_redirect(request, session)
    if early:
        return early
    settings = request.app.state.settings
    context = ui_state.resolve_context(settings, session)
    from game_companion.core.roster import importer

    try:
        parsed = importer.parse_roster_text(text, adapter_for(context.active_game))
        importer.stage_roster_import(
            session, adapter_for(context.active_game), context.active_game,
            context.player.id, parsed,
        )
        session.commit()
    except Exception as exc:
        session.rollback()
        return _redirect("/ui/imports", f"Import failed: {exc}")
    return _redirect(
        "/ui/imports",
        f"Staged {len(parsed['entries'])} entries ({len(parsed['unresolved'])} lines need attention) — review below",
    )


@router.post("/imports/upload")
async def imports_upload(
    request: Request,
    upload: UploadFile = File(...),
    screen_type: str = Form(...),
    character_hint: str = Form(""),
    session: Session = Depends(get_db),
):
    early = _needs_setup_redirect(request, session)
    if early:
        return early
    context = ui_state.resolve_context(request.app.state.settings, session)
    from game_companion.core.vision.service import ImportService

    raw = await upload.read()
    service = ImportService(session, adapter_for(context.active_game))
    try:
        result = service.create_import(
            context.active_game,
            context.player.id,
            screen_type=screen_type,
            image_base64=base64.b64encode(raw).decode(),
            screenshot_name=upload.filename,
            character_hint=character_hint.strip() or None,
            llm=request.app.state.llm,
        )
        session.commit()
    except Exception as exc:
        session.rollback()
        return _redirect("/ui/imports", f"Upload failed: {exc}")
    status = result["status"]
    suffix = f" — {result['error']}" if result.get("error") else ""
    return _redirect("/ui/imports", f"Screenshot {status}{suffix}")


@router.post("/imports/{import_id}/confirm")
def imports_confirm(request: Request, import_id: str, session: Session = Depends(get_db)):
    context = ui_state.resolve_context(request.app.state.settings, session)
    from game_companion.core.vision.service import ImportService

    try:
        ImportService(session, adapter_for(context.active_game)).confirm(import_id)
        session.commit()
    except Exception as exc:
        session.rollback()
        return _redirect("/ui/imports", f"Could not apply: {exc}")
    return _redirect("/ui/imports", "Changes applied")


@router.post("/imports/{import_id}/reject")
def imports_reject(request: Request, import_id: str, session: Session = Depends(get_db)):
    context = ui_state.resolve_context(request.app.state.settings, session)
    from game_companion.core.vision.service import ImportService

    try:
        ImportService(session, adapter_for(context.active_game)).reject(import_id)
        session.commit()
    except Exception as exc:
        session.rollback()
        return _redirect("/ui/imports", f"Could not discard: {exc}")
    return _redirect("/ui/imports", "Import discarded")


# -- inline editing (M21) --------------------------------------------------------------


@router.get("/roster/{ref}/edit", response_class=HTMLResponse)
def character_edit(request: Request, ref: str, session: Session = Depends(get_db)):
    early = _needs_setup_redirect(request, session)
    if early:
        return early
    context = ui_state.resolve_context(request.app.state.settings, session)
    adapter = adapter_for(context.active_game)
    service = RosterService(session, adapter)
    try:
        char = service.resolve_character(context.active_game, context.player.id, ref)
    except Exception:
        return _redirect("/ui/roster", "Character not found")
    from game_companion.api.serialize import character_dict

    record = character_dict(char)
    record["skills"] = dict(record["skills"])
    return _ctx(
        request,
        session,
        f"Edit {char.display_name}",
        "roster",
        template="character_edit.html",
        selected=record,
        choices=_character_field_choices(adapter),
        skill_defs={d.key: d.name for d in adapter.skill_definitions()},
        dupe_term=adapter.terminology().duplication,
        char_term=adapter.terminology().character,
    )


@router.post("/roster/{ref}/edit")
async def character_edit_save(request: Request, ref: str, session: Session = Depends(get_db)):
    context = ui_state.resolve_context(request.app.state.settings, session)
    adapter = adapter_for(context.active_game)
    service = RosterService(session, adapter)
    try:
        char = service.resolve_character(context.active_game, context.player.id, ref)
    except Exception:
        return _redirect("/ui/roster", "Character not found")

    from game_companion.utils import utcnow

    form = await request.form()
    patch: dict = {
        "display_name": str(form.get("display_name") or "").strip() or char.display_name,
        "owned": str(form.get("owned") or "") == "on",
        "favorite": str(form.get("favorite") or "") == "on",
        "notes": str(form.get("notes") or "").strip() or None,
        "verified": True,
    }
    # an emptied field means "clear it" — level/dupe/rarity go to None, and
    # data keys (attribute/specialty/faction) are removed from the merged dict
    patch["rarity"] = str(form.get("rarity") or "").strip() or None
    patch["level"] = int(form["level"]) if str(form.get("level") or "").strip() else None
    patch["duplication_level"] = (
        int(form["duplication_level"]) if str(form.get("duplication_level") or "").strip() else None
    )
    data_patch = {
        field: str(form.get(field) or "").strip() or None
        for field in _character_field_choices(adapter)
    }
    data_patch["faction"] = str(form.get("faction") or "").strip() or None
    merged = {**(char.data or {}), **{k: v for k, v in data_patch.items() if v is not None}}
    for key, value in data_patch.items():
        if value is None:
            merged.pop(key, None)  # cleared in the form → gone from the record
    patch["data"] = merged
    try:
        service.update_character(char, patch)
        skill_updates = {
            key.removeprefix("skill_"): int(value)
            for key, value in form.items()
            if key.startswith("skill_") and str(value).strip()
        }
        if skill_updates:
            service.set_skills(char, skill_updates)
        char.last_verified_at = utcnow()
        session.commit()
    except Exception as exc:
        session.rollback()
        return _redirect(f"/ui/roster/{char.key}/edit", f"Save failed: {exc}")
    return _redirect(f"/ui/roster/{char.key}/edit", f"{char.display_name} saved (verified today)")


@router.post("/resources/update")
def resource_update_ui(
    request: Request,
    resource_key: str = Form(...),
    quantity: int = Form(...),
    session: Session = Depends(get_db),
):
    context = ui_state.resolve_context(request.app.state.settings, session)
    if context.needs_setup:
        return _redirect("/ui")
    ResourceRepository(session).upsert(
        context.active_game, context.player.id, resource_key, quantity
    )
    session.commit()
    return _redirect("/ui/resources", f"{resource_key} set to {quantity}")


@router.post("/codes/{code_id}/toggle-used")
def code_toggle_used_ui(
    request: Request, code_id: str, session: Session = Depends(get_db)
):
    context = ui_state.resolve_context(request.app.state.settings, session)
    if context.needs_setup:
        return _redirect("/ui")
    service = CodeService(session, adapter_for(context.active_game))
    state = service.codes.player_state(code_id, context.player.id)
    marking_used = not (state.used if state else False)
    row = service.codes.get_or_raise(code_id, "code")
    service.mark_used(code_id, context.player.id, marking_used)
    session.commit()
    if marking_used:
        game = adapter_for(context.active_game)
        currency = game.theme().get("currency") or "code"
        return _redirect(
            "/ui/trackers#codes",
            f"{row.code} redeemed — enjoy the {currency}!",
        )
    return _redirect("/ui/trackers#codes")


@router.post("/teams/{team_id}/activate")
def team_activate_ui(request: Request, team_id: str, session: Session = Depends(get_db)):
    context = ui_state.resolve_context(request.app.state.settings, session)
    if context.needs_setup:
        return _redirect("/ui")
    service = TeamService(session, adapter_for(context.active_game))
    try:
        outcome = service.activate_team(service.teams.get_or_raise(team_id, "team"))
        session.commit()
    except Exception as exc:
        session.rollback()
        return _redirect("/ui/teams", f"Could not activate: {exc}")
    detail = outcome.get("deactivated") or []
    note = f" (also deactivated: {', '.join(detail)})" if detail else ""
    return _redirect("/ui/teams", f"Team activated{note}")


@router.post("/teams/{team_id}/deactivate")
def team_deactivate_ui(request: Request, team_id: str, session: Session = Depends(get_db)):
    context = ui_state.resolve_context(request.app.state.settings, session)
    if context.needs_setup:
        return _redirect("/ui")
    team = TeamRepository(session).get_or_raise(team_id, "team")
    team.is_active = False
    session.commit()
    return _redirect("/ui/teams", "Team deactivated")


# -- games management (M25) -----------------------------------------------------------


@router.get("/games", response_class=HTMLResponse)
def games_page(request: Request, session: Session = Depends(get_db)):
    early = _needs_setup_redirect(request, session)
    if early:
        return early
    settings = request.app.state.settings
    context = ui_state.resolve_context(settings, session)
    active_game = context.active_game
    rows = []
    for a in list_adapters():
        service = CatalogService(session, a)
        codes_source = a.codes_source()
        codes_run = service.run_for(codes_source["key"]) if codes_source else None
        rows.append(
            {
                "game_id": a.game_id,
                "display_name": a.display_name,
                "version": a.version,
                "theme": a.theme(),
                "is_active": a.game_id == active_game,
                "catalog_counts": service.counts(),
                "has_codes": bool(codes_source),
                "codes_status": codes_run.status if codes_run else None,
                "codes_at": to_iso(codes_run.fetched_at)[:16].replace("T", " ") if codes_run and codes_run.fetched_at else None,
                "sources": [
                    {"key": k, "entity": spec.get("entity", "")}
                    for k, spec in sorted(a.catalog_sources().items())
                ],
            }
        )
    # data-management section for the active game (absorbed from the old
    # Database page): catalog runs + staged change review
    adapter = adapter_for(active_game)
    catalog_service = CatalogService(session, adapter)
    return _ctx(
        request,
        session,
        "Games",
        "games",
        template="games.html",
        game_rows=rows,
        active_display=adapter.display_name,
        char_term=adapter.terminology().character,
        char_term_plural=adapter.terminology().character_plural,
        catalog_counts=catalog_service.counts(),
        catalog_runs=[
            {
                "key": r.source_key,
                "kind": r.kind,
                "status": r.status,
                "detail": r.detail,
                "item_count": r.items,
                "fetched_at": to_iso(r.fetched_at)[:16].replace("T", " ") if r.fetched_at else None,
            }
            for r in catalog_service.runs()
        ],
        pending_changes=_pending_changes(session, active_game),
    )


@router.post("/games/create")
def games_create(request: Request, game_id: str = Form(...), display_name: str = Form(...), session: Session = Depends(get_db)):
    """Scaffold a new game adapter in-app (no terminal)."""
    import re as _re

    from game_companion.core.games import scaffold

    clean_id = game_id.strip().lower().replace(" ", "_")
    if not _re.fullmatch(r"[a-z0-9_]{2,30}", clean_id):
        return _redirect("/ui/games", "Game id: 2–30 lowercase letters, digits, underscores")
    games_root = Path(scaffold.__file__).resolve().parent.parent.parent / "games"
    try:
        scaffold.scaffold_new_game(clean_id, games_root)
        scaffold.register_installed(clean_id, games_root)
    except Exception as exc:
        return _redirect("/ui/games", f"Could not create game: {exc}")
    return _redirect("/ui/games", f"{display_name.strip()} ({clean_id}) created — switch to it from the game picker")


@router.post("/games/{game_id}/refresh-catalog")
def games_refresh_catalog(request: Request, game_id: str, session: Session = Depends(get_db)):
    try:
        adapter = adapter_for(game_id)
    except Exception:
        return _redirect("/ui/games", "Unknown game")
    service = CatalogService(session, adapter)
    try:
        summary = service.refresh(
            "auto", transport=getattr(request.app.state, "llm_transport", None)
        )
        session.commit()
    except Exception as exc:
        session.rollback()
        return _redirect("/ui/games", f"Catalog import failed: {exc}")
    if not summary:
        return _redirect("/ui/games", f"{adapter.display_name} declares no catalog sources yet")
    ok = [k for k, v in summary.items() if v["status"] == "ok"]
    bad = [k for k, v in summary.items() if v["status"] != "ok"]
    parts = [f"{len(ok)} source(s) imported"] + ([f"unavailable: {', '.join(bad)}"] if bad else [])
    return _redirect("/ui/games", f"{adapter.display_name} catalog — " + ", ".join(parts))


@router.post("/games/{game_id}/refresh-codes")
def games_refresh_codes(request: Request, game_id: str, session: Session = Depends(get_db)):
    try:
        adapter = adapter_for(game_id)
    except Exception:
        return _redirect("/ui/games", "Unknown game")
    try:
        summary = CodeService(session, adapter).refresh_from_source(
            transport=getattr(request.app.state, "llm_transport", None)
        )
        session.commit()
    except Exception as exc:
        session.rollback()
        return _redirect("/ui/games", f"Codes refresh failed: {exc}")
    if summary["status"] != "ok":
        return _redirect("/ui/games", f"{adapter.display_name}: {summary.get('detail', 'no codes source')}")
    return _redirect("/ui/games", f"{adapter.display_name} codes refreshed ({summary['added']} new)")


# -- chat + personas (M22) ----------------------------------------------------------


def _chat_service(request: Request, session: Session):
    context = ui_state.resolve_context(request.app.state.settings, session)
    from game_companion.core.chat.service import ChatService

    service = ChatService(
        session,
        adapter_for(context.active_game),
        context.player.id if context.player else "",
        request.app.state.llm,
    )
    return context, service


@router.get("/chat", response_class=HTMLResponse)
def chat_page(request: Request, c: str = "", session: Session = Depends(get_db)):
    """Chat lives on Home now; old links land there."""
    return _redirect(f"/ui?c={c}" if c else "/ui")


@router.post("/chat/new")
def chat_new(request: Request, persona_id: str = Form(""), session: Session = Depends(get_db)):
    context, service = _chat_service(request, session)
    if context.needs_setup:
        return _redirect("/ui")
    conv = service.create_conversation(persona_id=persona_id or None)
    session.commit()
    return _redirect(f"/ui?c={conv.id}")


@router.post("/chat/{conversation_id}/send")
def chat_send(request: Request, conversation_id: str, text: str = Form(...), session: Session = Depends(get_db)):
    context, service = _chat_service(request, session)
    if context.needs_setup:
        return _redirect("/ui")
    try:
        service.send(conversation_id, text)
    except Exception as exc:
        # keep the typed message and the "(chat failed: …)" marker the service
        # wrote — the user's input must not silently vanish from the transcript
        session.commit()
        return _redirect(f"/ui?c={conversation_id}", f"Chat error: {exc}")
    session.commit()
    return _redirect(f"/ui?c={conversation_id}")


@router.post("/chat/{conversation_id}/persona")
def chat_persona(request: Request, conversation_id: str, persona_id: str = Form(""), session: Session = Depends(get_db)):
    context, service = _chat_service(request, session)
    if context.needs_setup:
        return _redirect("/ui")
    conv = service.get_conversation(conversation_id)
    conv.persona_id = persona_id or None
    session.commit()
    return _redirect(f"/ui?c={conversation_id}", "Persona updated")


@router.post("/chat/{conversation_id}/delete")
def chat_delete(request: Request, conversation_id: str, session: Session = Depends(get_db)):
    context, service = _chat_service(request, session)
    if context.needs_setup:
        return _redirect("/ui")
    try:
        service.delete_conversation(conversation_id)
        session.commit()
    except Exception:
        session.rollback()
    return _redirect("/ui")


# -- persona editor -------------------------------------------------------------------


@router.get("/personas", response_class=HTMLResponse)
def personas_page(request: Request, session: Session = Depends(get_db)):
    early = _needs_setup_redirect(request, session)
    if early:
        return early
    from game_companion.core.persona.store import PersonaStore

    store = PersonaStore(request.app.state.settings)
    games = [{"game_id": a.game_id, "display_name": a.display_name} for a in list_adapters()]
    context = ui_state.resolve_context(request.app.state.settings, session)
    adapter = adapter_for(context.active_game)
    return _ctx(
        request,
        session,
        "Personas",
        "personas",
        template="personas.html",
        personas=store.list_personas(),
        games=games,
        current_game=context.active_game,
        catalog_chars=[
            {"key": e.key, "display_name": e.display_name}
            for e in CatalogService(session, adapter).entries("character")
        ],
        char_term=adapter.terminology().character,
    )


@router.post("/personas/save")
def personas_save(
    request: Request,
    persona_id: str = Form(...),
    name: str = Form(...),
    description: str = Form(""),
    tone: str = Form("friendly"),
    verbosity: str = Form("medium"),
    style_traits: str = Form(""),
    example_phrases: str = Form(""),
    system_preamble: str = Form(""),
    bound_game: str = Form(""),
    role_as_character: str = Form(""),
    session: Session = Depends(get_db),
):
    from game_companion.core.persona.schema import PersonaConfig
    from game_companion.core.persona.store import PersonaStore

    store = PersonaStore(request.app.state.settings)
    traits = [t.strip() for t in style_traits.replace(";", ",").split(",") if t.strip()]
    phrases = [p.strip() for p in example_phrases.splitlines() if p.strip()]
    role_as_name = None
    if role_as_character:
        context = ui_state.resolve_context(request.app.state.settings, session)
        entry = CatalogService(session, adapter_for(context.active_game)).find(
            "character", role_as_character
        )
        role_as_name = entry.display_name if entry else None
    try:
        persona = PersonaConfig(
            id=persona_id.strip(),
            name=name.strip(),
            description=description.strip(),
            tone=tone,
            verbosity=verbosity,
            style_traits=traits,
            example_phrases=phrases,
            system_preamble=system_preamble,
            bound_game=bound_game or None,
            role_as_character=role_as_character or None,
            role_as_name=role_as_name,
        )
        store.save(persona)
    except Exception as exc:
        return _redirect("/ui/personas", f"Could not save persona: {exc}")
    label = f"role-playing as {role_as_name}" if role_as_name else persona.name
    return _redirect("/ui/personas", f"Persona '{label}' saved")


@router.post("/personas/quick-character")
def personas_quick_character(
    request: Request,
    character_key: str = Form(...),
    session: Session = Depends(get_db),
):
    """One-click: 'I want Jane Doe' → a persona that speaks as that character."""
    from game_companion.core.persona.schema import PersonaConfig
    from game_companion.core.persona.store import PersonaStore

    context = ui_state.resolve_context(request.app.state.settings, session)
    adapter = adapter_for(context.active_game)
    entry = CatalogService(session, adapter).find("character", character_key)
    if entry is None:
        return _redirect("/ui/personas", "Pick a name from the catalog")
    persona_id = f"as_{entry.key}"
    persona = PersonaConfig(
        id=persona_id,
        name=f"As {entry.display_name}",
        description=f"Speaks as {entry.display_name} from {adapter.display_name}.",
        tone="playful",
        verbosity="medium",
        bound_game=adapter.game_id,
        role_as_character=entry.key,
        role_as_name=entry.display_name,
    )
    PersonaStore(request.app.state.settings).save(persona)
    return _redirect("/ui/personas", f"Persona '{persona.name}' created — pick it when starting a chat")


@router.post("/personas/{persona_id}/delete")
def personas_delete(request: Request, persona_id: str, session: Session = Depends(get_db)):
    from game_companion.core.persona.store import PersonaStore

    store = PersonaStore(request.app.state.settings)
    if store.delete_file(persona_id):
        return _redirect("/ui/personas", f"Persona '{persona_id}' deleted")
    return _redirect("/ui/personas", "Built-in personas can be overridden by saving one with the same id, but not deleted")


@router.post("/memories/add")
def memories_add(request: Request, content: str = Form(...), session: Session = Depends(get_db)):
    context, service = _chat_service(request, session)
    if context.needs_setup:
        return _redirect("/ui")
    try:
        service.add_memory(content, source="manual")
        session.commit()
    except Exception as exc:
        session.rollback()
        return _redirect("/ui/settings", f"Could not add memory: {exc}")
    return _redirect("/ui/settings", "Memory saved")


@router.post("/memories/{memory_id}/toggle")
def memories_toggle(request: Request, memory_id: str, session: Session = Depends(get_db)):
    context, service = _chat_service(request, session)
    if context.needs_setup:
        return _redirect("/ui")
    row = session.get(CompanionMemory, memory_id)
    if row is not None and row.player_profile_id == context.player.id:
        row.active = not row.active
        session.commit()
    return _redirect("/ui/settings")


@router.post("/memories/{memory_id}/delete")
def memories_delete(request: Request, memory_id: str, session: Session = Depends(get_db)):
    context, service = _chat_service(request, session)
    if context.needs_setup:
        return _redirect("/ui")
    row = session.get(CompanionMemory, memory_id)
    if row is not None and row.player_profile_id == context.player.id:
        session.delete(row)
        session.commit()
    return _redirect("/ui/settings", "Memory deleted")


# -- database page (character browser/editor + game-data updates) ---------------------


def _character_field_choices(adapter):
    return adapter.character_field_choices() or {}


@router.get("/database", response_class=HTMLResponse)
def database_page(request: Request, character: str = "", new: str = "", session: Session = Depends(get_db)):
    """The Database page dissolved: agent editing lives on the Agents pages,
    catalog/data-update panels live on the Games page."""
    return _redirect("/ui/games#data")



def _pending_changes(session: Session, game_id: str) -> list[dict]:
    from game_companion.db.repositories import ResearchRepository

    rows = ResearchRepository(session).changes(game_id, "pending")
    return [
        {
            "id": c.id,
            "entity_type": c.entity_type,
            "entity_key": c.entity_key,
            "is_new": c.previous_value is None,
            "proposed": c.proposed_value,
            "evidence": (c.evidence or [{}])[0] if c.evidence else {},
        }
        for c in rows
    ]


@router.post("/roster/create")
def roster_create(request: Request, catalog_key: str = Form(""), key: str = Form(""), display_name: str = Form(""), session: Session = Depends(get_db)):
    context = ui_state.resolve_context(request.app.state.settings, session)
    if context.needs_setup:
        return _redirect("/ui")
    adapter = adapter_for(context.active_game)
    service = RosterService(session, adapter)
    catalog_service = CatalogService(session, adapter)

    def _done(created_key: str, name: str):
        session.commit()
        return _redirect(f"/ui/roster/{created_key}/edit", f"{name} created — fill in whatever you know")

    if catalog_key:
        entry = catalog_service.find("character", catalog_key)
        if entry is None:
            return _redirect("/ui/roster?new=1", "Pick a name from the list")
        try:
            choices = adapter.character_field_choices()
            data = {k: v for k, v in (entry.meta or {}).items() if k in choices and v}
            char = service.create_character(
                context.active_game, context.player.id,
                {"key": entry.key, "display_name": entry.display_name, "data": data},
            )
            service.update_character(char, {"owned": True, "source": "catalog"})
        except Exception as exc:
            session.rollback()
            return _redirect("/ui/roster?new=1", f"Could not create: {exc}")
        return _done(entry.key, entry.display_name)

    clean_key = key.strip().lower().replace(" ", "_")
    try:
        service.create_character(
            context.active_game, context.player.id,
            {"key": clean_key, "display_name": display_name.strip() or clean_key},
        )
    except Exception as exc:
        session.rollback()
        return _redirect("/ui/roster?new=1", f"Could not create: {exc}")
    return _done(clean_key, clean_key)


@router.post("/games/data/check-updates")
def database_check_updates(request: Request, session: Session = Depends(get_db)):
    context = ui_state.resolve_context(request.app.state.settings, session)
    if context.needs_setup:
        return _redirect("/ui")
    adapter = adapter_for(context.active_game)
    notes = []
    try:
        catalog_summary = CatalogService(session, adapter).refresh(
            "auto", transport=getattr(request.app.state, "llm_transport", None)
        )
        ok = [k for k, v in catalog_summary.items() if v["status"] == "ok"]
        bad = [k for k, v in catalog_summary.items() if v["status"] != "ok"]
        notes.append(f"catalog updated ({len(ok)} ok)" + (f", unavailable: {', '.join(bad)}" if bad else ""))
    except Exception as exc:
        notes.append(f"catalog import failed: {exc}")
    try:
        from game_companion.core.research.service import ResearchService

        outcome = ResearchService(session, adapter).check_sources()
        notes.append(f"sources checked: {outcome}")
    except Exception as exc:
        notes.append(f"source check failed: {exc}")
    if adapter.bootstrap_sources():
        try:
            from game_companion.config import get_settings
            from game_companion.core.bootstrap.pipeline import BootstrapService

            summary = BootstrapService(session, adapter, get_settings()).run(
                "auto", apply=False, transport=getattr(request.app.state, "llm_transport", None)
            )
            notes.append(f"bootstrap staged {summary.get('staged', 0)} rows from {summary.get('source')}")
        except Exception as exc:
            notes.append(f"bootstrap failed: {exc}")
    session.commit()
    return _redirect("/ui/games#data", " · ".join(notes))


@router.post("/games/data/changes/{change_id}/approve")
def database_change_approve(request: Request, change_id: str, session: Session = Depends(get_db)):
    context = ui_state.resolve_context(request.app.state.settings, session)
    if context.needs_setup:
        return _redirect("/ui")
    try:
        from game_companion.core.research.service import ResearchService

        ResearchService(session, adapter_for(context.active_game)).decide_change(change_id, approve=True)
        session.commit()
    except Exception as exc:
        session.rollback()
        return _redirect("/ui/games#data", f"Approve failed: {exc}")
    return _redirect("/ui/games#data", "Change approved and applied")


@router.post("/games/data/changes/{change_id}/reject")
def database_change_reject(request: Request, change_id: str, session: Session = Depends(get_db)):
    context = ui_state.resolve_context(request.app.state.settings, session)
    if context.needs_setup:
        return _redirect("/ui")
    try:
        from game_companion.core.research.service import ResearchService

        ResearchService(session, adapter_for(context.active_game)).decide_change(change_id, approve=False)
        session.commit()
    except Exception as exc:
        session.rollback()
        return _redirect("/ui/games#data", f"Reject failed: {exc}")
    return _redirect("/ui/games#data", "Change rejected")
