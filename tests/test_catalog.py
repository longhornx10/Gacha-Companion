"""M25: reference catalog, auto-refreshed codes, in-app game management.

Every online-source test goes through fixtures or an httpx MockTransport —
the suite never touches the network.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "catalog"


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


# -- adapters: source declarations ---------------------------------------------------


def test_games_declare_catalog_and_codes_sources():
    from game_companion.core.games.registry import get_adapter

    zzz = get_adapter("zzz")
    zzz_entities = {s["entity"] for s in zzz.catalog_sources().values()}
    assert {"character", "equipment", "banner"} <= zzz_entities
    assert all(s["url"].startswith("https://www.prydwen.gg/zenless") for s in zzz.catalog_sources().values())
    assert zzz.codes_source()["url"].startswith("https://zenlesscodes.com")

    hsr = get_adapter("hsr")
    entities = {s["entity"] for s in hsr.catalog_sources().values()}
    assert {"character", "equipment", "gear_set", "banner"} <= entities
    assert hsr.codes_source()["url"] == "https://www.prydwen.gg/star-rail"

    nte = get_adapter("nte")
    assert nte.codes_source()["url"].startswith("https://www.prydwen.gg")

    example = get_adapter("example")
    assert example.catalog_sources() == {} and example.codes_source() is None


# -- parser unit tests (fixtures captured from the live sources) ----------------------


def test_zenlesscodes_transform_parses_active_and_expired():
    from game_companion.games.zzz import catalog as zzz_catalog

    rows = zzz_catalog.codes_transform(json.loads(_fixture("zenlesscodes_codes.json")))
    by_status = {row["code"]: row["status"] for row in rows}
    assert "active" in set(by_status.values()) and "expired" in set(by_status.values())
    active = [r for r in rows if r["status"] == "active"]
    assert all(r["discovered_at"] is not None for r in active if r.get("discovered_at"))


def test_zenlesscodes_transform_rejects_garbage():
    from game_companion.games.zzz import catalog as zzz_catalog

    assert zzz_catalog.codes_transform("not json") == []
    assert zzz_catalog.codes_transform({"codes": None}) == []


def test_prydwen_nte_characters_transform():
    from game_companion.games.nte import catalog as nte_catalog

    rows = nte_catalog.catalog_transform(
        "prydwen_characters", _fixture("prydwen_nte_characters.html")
    )
    assert rows, "fixture must yield rows"
    adler = [r for r in rows if r["name"] == "Adler"][0]
    assert adler["key"] == "adler"
    assert adler["rarity"] == "A"
    assert adler["meta"]["role"] in ("Buff", "Damage", "Survival")


def test_prydwen_nte_codes_transform():
    from game_companion.games.nte import catalog as nte_catalog

    rows = nte_catalog.codes_transform(_fixture("prydwen_nte_codes.html"))
    codes = {r["code"] for r in rows}
    assert "NTEGIFT" in codes
    assert all(r["status"] == "active" for r in rows)
    discovered = [r["discovered_at"] for r in rows if r["discovered_at"]]
    assert discovered, "release dates should parse"


def test_prydwen_hsr_codes_transform():
    from game_companion.games.hsr import catalog as hsr_catalog

    rows = hsr_catalog.codes_transform(_fixture("prydwen_hsr_home.html"))
    assert [r["code"] for r in rows] == ["STARRAILGIFT"]
    assert rows[0]["status"] == "active"
    assert "Stellar Jade" in rows[0]["rewards"]
    assert rows[0]["discovered_at"] is not None


def test_prydwen_codes_expired_header_flips_status():
    from game_companion.core.games.prydwen import parse_codes

    html = (
        '<p class="code">GOODONE</p><p class="rewards">50</p>'
        '<p class="date">Released on 01.02.2025</p>'
        "<h2>Expired codes</h2>"
        '<p class="code">OLDONE</p><p class="rewards">10</p>'
        '<p class="date">Released on 01.02.2024</p>'
    )
    rows = parse_codes(html)
    by_code = {r["code"]: r["status"] for r in rows}
    assert by_code == {"GOODONE": "active", "OLDONE": "expired"}


def test_starrailres_characters_transform():
    from game_companion.games.hsr import catalog as hsr_catalog

    rows = hsr_catalog.catalog_transform(
        "starrailres_characters", json.loads(_fixture("starrailres_characters.json"))
    )
    march = [r for r in rows if r["name"] == "March 7th"][0]
    assert march["rarity"] == 4
    assert march["meta"]["element"] == "Ice"


def test_starrailres_transform_skips_trailblazer_placeholders():
    """{NICKNAME} entries are the player, not characters — never catalog them."""
    from game_companion.games.hsr import catalog as hsr_catalog

    payload = json.loads(_fixture("starrailres_characters.json"))
    payload["8001"] = {"name": "{NICKNAME}", "rarity": 5, "path": "Destruction"}
    rows = hsr_catalog.catalog_transform("starrailres_characters", payload)
    assert all("{" not in r["name"] for r in rows)
    assert all(r["key"] != "8001" for r in rows)


def test_prydwen_zzz_characters_transform():
    from game_companion.games.zzz import catalog as zzz_catalog

    rows = zzz_catalog.catalog_transform(
        "prydwen_characters", _fixture("prydwen_zzz_characters.html")
    )
    by_key = {r["key"]: r for r in rows}
    assert "alice" in by_key and "anby_demara" in by_key
    alice = by_key["alice"]
    assert alice["name"] == "Alice"
    assert alice["rarity"] == 5 and alice["meta"]["rank"] == "S"
    assert alice["meta"]["attribute"] == "physical"
    assert alice["meta"]["specialty"] == "anomaly"


def test_prydwen_zzz_wengines_transform():
    from game_companion.games.zzz import catalog as zzz_catalog

    rows = zzz_catalog.catalog_transform(
        "prydwen_wengines", _fixture("prydwen_zzz_wengines.html")
    )
    by_key = {r["key"]: r for r in rows}
    assert "angel_in_the_shell" in by_key
    engine = by_key["angel_in_the_shell"]
    assert engine["name"] == "Angel in the Shell"
    assert engine["rarity"] == 5
    assert engine["meta"]["kind"] == "wengine"


def test_zzz_defence_spelling_normalized():
    from game_companion.games.zzz import catalog as zzz_catalog

    html = _fixture("prydwen_zzz_characters.html").replace(
        "Anby Stun style", "Anby Defence style"
    )
    rows = zzz_catalog.catalog_transform("prydwen_characters", html)
    anby = [r for r in rows if r["key"] == "anby_demara"][0]
    assert anby["meta"]["specialty"] == "defense"


def test_prydwen_banners_transform():
    from game_companion.games.zzz import catalog as zzz_catalog

    rows = zzz_catalog.catalog_transform(
        "prydwen_banners", _fixture("prydwen_banners.html")
    )
    by_key = {r["key"]: r for r in rows}
    # dated cards only — the teased, undated ones are skipped, never guessed
    assert len(rows) == 4

    claret = by_key["claret_2026-09-09"]
    assert claret["name"] == "Claret"
    assert claret["rarity"] == 5
    assert claret["meta"]["section"] == "current"
    assert claret["meta"]["kind"] == "character"
    assert claret["meta"]["banner_type"] == "new"
    assert claret["meta"]["starts_at"] == "2026-09-09T03:00:00Z"
    assert claret["meta"]["ends_at"] == "2026-09-30T16:59:00Z"
    assert claret["meta"]["phase"] == "Patch 3.2 Phase 1"
    assert claret["meta"]["art"].startswith("https://cdn.prydwen.gg/")
    assert claret["meta"]["featured"] == [{"name": "Claret", "path": "/zenless/characters/claret"}]

    engine = by_key["1788884982610-d7a58f04b2047e93f9244438ede5bd65_2026-09-09"]
    assert engine["meta"]["kind"] == "weapon"

    roxy = by_key["roxy_2026-09-30"]
    assert roxy["meta"]["section"] == "upcoming"


def test_all_live_games_declare_banner_sources():
    from game_companion.core.games.registry import get_adapter

    for gid in ("zzz", "hsr", "nte"):
        sources = get_adapter(gid).catalog_sources()
        banner = [s for s in sources.values() if s.get("entity") == "banner"]
        assert banner, gid
        assert banner[0]["kind"] == "html"
        assert banner[0]["url"].endswith("/banners")


def test_hsr_and_nte_banner_transforms_share_the_parser():
    from game_companion.games.hsr import catalog as hsr_catalog
    from game_companion.games.nte import catalog as nte_catalog

    html = _fixture("prydwen_banners.html")
    assert hsr_catalog.catalog_transform("prydwen_banners", html)
    assert nte_catalog.catalog_transform("prydwen_banners", html)
    # unknown keys still return nothing rather than guessing
    assert hsr_catalog.catalog_transform("prydwen_banners", {"not": "html"}) == []


# -- CatalogService against a mock transport ------------------------------------------


@pytest.fixture()
def zzz_transport():
    """Serves every ZZZ source from fixtures; unknown URLs are 'blocked'."""
    codes_payload = json.loads(_fixture("zenlesscodes_codes.json"))
    chars_html = _fixture("prydwen_zzz_characters.html")
    engines_html = _fixture("prydwen_zzz_wengines.html")
    banners_html = _fixture("prydwen_banners.html")

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.endswith("/zenless/characters"):
            return httpx.Response(200, text=chars_html)
        if url.endswith("/zenless/w-engines"):
            return httpx.Response(200, text=engines_html)
        if url.endswith("/zenless/banners"):
            return httpx.Response(200, text=banners_html)
        if "zenlesscodes.com" in url:
            return httpx.Response(200, json=codes_payload)
        return httpx.Response(403, text="blocked")

    return httpx.MockTransport(handler)


def test_catalog_refresh_upserts_and_records_ok_run(client, zzz_transport):
    from game_companion.core.catalog.service import CatalogService
    from game_companion.core.games.registry import get_adapter
    from game_companion.db.session import create_session_factory

    adapter = get_adapter("zzz")
    session = create_session_factory(client.app.state.engine)()
    service = CatalogService(session, adapter)

    summary = service.refresh("auto", transport=zzz_transport)
    assert summary["prydwen_characters"]["status"] == "ok"
    assert summary["prydwen_characters"]["added"] == 2  # fixture holds 2 agent cards
    session.commit()

    entry = service.find("character", "alice")
    assert entry.display_name == "Alice"
    assert entry.meta["attribute"] == "physical"
    assert entry.meta["specialty"] == "anomaly"

    # changed payload + re-run: updates in place, never duplicates
    service.session.close()

    renamed = _fixture("prydwen_zzz_characters.html").replace(
        '<span class="emp-name">Alice</span>', '<span class="emp-name">Alice Thymefield</span>'
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=renamed)

    session = create_session_factory(client.app.state.engine)()
    service = CatalogService(session, adapter)
    summary = service.refresh("auto", transport=httpx.MockTransport(handler))
    assert summary["prydwen_characters"]["updated"] == 2
    assert summary["prydwen_characters"]["added"] == 0
    run = service.run_for("prydwen_characters")
    assert run.status == "ok" and run.items == 2
    session.close()


def test_catalog_refresh_records_error_but_does_not_block(client, zzz_transport):
    """A blocked source is recorded honestly; the others still import."""
    from game_companion.core.catalog.service import CatalogService
    from game_companion.core.games.registry import get_adapter
    from game_companion.db.session import create_session_factory

    # characters resolve, w-engines are "blocked" — the good source must win
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url).endswith("/zenless/w-engines"):
            return httpx.Response(403, text="forbidden")
        return httpx.Response(200, text=_fixture("prydwen_zzz_characters.html"))

    adapter = get_adapter("zzz")
    session = create_session_factory(client.app.state.engine)()
    service = CatalogService(session, adapter)
    summary = service.refresh("auto", transport=httpx.MockTransport(handler))
    assert summary["prydwen_characters"]["status"] == "ok"
    assert summary["prydwen_wengines"]["status"] == "error"
    run = service.run_for("prydwen_wengines")
    assert run.status == "error" and "403" in (run.detail or "")
    session.close()


# -- codes auto-refresh ----------------------------------------------------------------


def test_codes_refresh_from_source_preserves_used_state(client, ui_player, zzz_transport):
    from game_companion.core.codes.service import CodeService
    from game_companion.core.games.registry import get_adapter
    from game_companion.db.session import create_session_factory

    session = create_session_factory(client.app.state.engine)()
    adapter = get_adapter("zzz")
    service = CodeService(session, adapter)
    first = service.refresh_from_source(transport=zzz_transport)
    assert first["status"] == "ok"
    assert first["items"] == 8  # 5 active + 3 expired in the fixture
    session.commit()
    session.close()

    session = create_session_factory(client.app.state.engine)()
    service = CodeService(session, adapter)
    code_row, _ = service.list_codes(ui_player)[0]
    watched_code = code_row.code
    service.mark_used(code_row.id, ui_player, True)
    session.commit()
    session.close()

    # source flips the watched code to expired — used-state must survive
    def expired_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"codes": [], "expired": [{"code": watched_code, "status": "expired"}]}
        )

    session = create_session_factory(client.app.state.engine)()
    service = CodeService(session, adapter)
    second = service.refresh_from_source(transport=httpx.MockTransport(expired_handler))
    assert second["status"] == "ok"
    session.commit()
    rows = {c.code: (c, s) for c, s in service.list_codes(ui_player)}
    code_row, state = rows[watched_code]
    assert code_row.status == "expired"
    assert state.used is True
    session.close()


def test_codes_refresh_records_when_game_has_no_source(client):
    from game_companion.core.catalog.service import CatalogService
    from game_companion.core.codes.service import CodeService
    from game_companion.core.games.registry import get_adapter
    from game_companion.db.session import create_session_factory

    session = create_session_factory(client.app.state.engine)()
    service = CodeService(session, get_adapter("example"))
    summary = service.refresh_from_source()
    assert summary["status"] == "error"
    run = CatalogService(session, get_adapter("example")).run_for("codes")
    assert run is not None and run.status == "error"
    session.close()


# -- scheduler --------------------------------------------------------------------------


def test_run_due_refreshes_fetches_stale_sources_only(client, zzz_transport):
    from game_companion.core.catalog.scheduler import run_due_refreshes
    from game_companion.core.catalog.service import CatalogService
    from game_companion.core.games.registry import get_adapter
    from game_companion.db.session import create_session_factory

    client.app.state.llm_transport = zzz_transport
    calls = {"n": 0}
    original = zzz_transport.handler

    def counting(request):
        calls["n"] += 1
        return original(request)

    zzz_transport.handler = counting

    # fresh run first (seeds ok runs) — zzz sources now recent, nothing due
    run_due_refreshes(client.app)
    fresh = calls["n"]
    assert fresh > 0

    # backdate the codes run past 24h — only codes should refetch
    session = create_session_factory(client.app.state.engine)()
    adapter = get_adapter("zzz")
    service = CatalogService(session, adapter)
    run = service.run_for("zenlesscodes")
    run.fetched_at = datetime.now(UTC) - timedelta(hours=25)
    session.commit()
    session.close()

    calls["n"] = 0
    run_due_refreshes(client.app)
    assert calls["n"] >= 1
    session = create_session_factory(client.app.state.engine)()
    assert CatalogService(session, adapter).run_for("zenlesscodes").status == "ok"
    session.close()


def test_run_due_refreshes_banners_on_shorter_cadence(client, zzz_transport):
    """Banner windows go stale on hours, not weeks — Home shows them live."""
    from game_companion.core.catalog.scheduler import BANNER_MAX_AGE, run_due_refreshes
    from game_companion.core.catalog.service import CatalogService
    from game_companion.core.games.registry import get_adapter
    from game_companion.db.session import create_session_factory

    client.app.state.llm_transport = zzz_transport
    calls = {"n": 0, "urls": []}
    original = zzz_transport.handler

    def counting(request):
        calls["n"] += 1
        calls["urls"].append(str(request.url))
        return original(request)

    zzz_transport.handler = counting
    run_due_refreshes(client.app)  # fresh run seeds ok runs for every source

    session = create_session_factory(client.app.state.engine)()
    adapter = get_adapter("zzz")
    service = CatalogService(session, adapter)
    banner_run = service.run_for("prydwen_banners")
    assert banner_run is not None and banner_run.status == "ok"
    # backdate banners past their cadence but under the weekly catalog age
    banner_run.fetched_at = datetime.now(UTC) - BANNER_MAX_AGE - timedelta(minutes=5)
    session.commit()
    session.close()

    calls["n"] = 0
    calls["urls"] = []
    run_due_refreshes(client.app)
    # zzz refetches exactly its banners source; hsr/nte keep erroring on the
    # blocked transport every tick (error runs are always stale) — not our concern
    zzz_calls = [u for u in calls["urls"] if "/zenless/" in u]
    assert zzz_calls == ["https://www.prydwen.gg/zenless/banners"], calls["urls"]
    session = create_session_factory(client.app.state.engine)()
    refreshed = CatalogService(session, adapter).run_for("prydwen_banners")
    assert (datetime.now(UTC).replace(tzinfo=None) - refreshed.fetched_at.replace(tzinfo=None)) < timedelta(minutes=1)
    session.close()


# -- UI: catalog-driven flows ------------------------------------------------------------


def test_roster_add_from_catalog(client, ui_player, zzz_transport):
    from game_companion.core.catalog.service import CatalogService
    from game_companion.core.games.registry import get_adapter
    from game_companion.db.session import create_session_factory

    session = create_session_factory(client.app.state.engine)()
    CatalogService(session, get_adapter("zzz")).refresh("auto", transport=zzz_transport)
    session.commit()
    session.close()

    page = client.get("/ui/roster")
    assert "Alice" in page.text
    added = client.post(
        "/ui/roster/add",
        data={"catalog_key": "alice", "level": "60", "duplication_level": "1"},
        follow_redirects=True,
    )
    assert "added" in added.text
    char = client.get("/api/games/zzz/characters/alice").json()
    assert char["owned"] is True
    assert char["level"] == 60


def test_gear_add_equipment_and_piece_from_catalog(client, ui_player, zzz_transport):
    from game_companion.core.catalog.service import CatalogService
    from game_companion.core.games.registry import get_adapter
    from game_companion.db.session import create_session_factory

    session = create_session_factory(client.app.state.engine)()
    CatalogService(session, get_adapter("zzz")).refresh("auto", transport=zzz_transport)
    session.commit()
    session.close()

    page = client.get("/ui/gear")
    assert "Angel in the Shell" in page.text

    added = client.post(
        "/ui/gear/equipment/add",
        data={"catalog_key": "angel_in_the_shell", "level": "50", "refinement": "1"},
        follow_redirects=True,
    )
    assert "added" in added.text
    equipment = client.get("/api/games/zzz/equipment").json()["equipment"]
    assert any(e["display_name"] == "Angel in the Shell" and e["level"] == 50 for e in equipment)

    piece = client.post(
        "/ui/gear/gear/add",
        data={"set_key": "woodpecker", "slot": "1", "rarity": "5", "level": "15",
              "main_stat_key": "hp", "main_stat_value": "3000"},
        follow_redirects=True,
    )
    assert "added" in piece.text


def test_database_import_catalog_and_status(client, ui_player, zzz_transport):
    """The old Database panels live on the Games page now."""
    client.app.state.llm_transport = zzz_transport
    result = client.post("/ui/games/zzz/refresh-catalog", follow_redirects=True)
    assert "catalog" in result.text
    page = client.get("/ui/games")
    assert "prydwen_characters" in page.text  # source runs table
    assert "2 characters" in page.text  # fixture holds 2 agent cards


def test_codes_page_shows_source_and_refresh(client, ui_player, zzz_transport):
    client.app.state.llm_transport = zzz_transport
    refreshed = client.post("/ui/codes/refresh", follow_redirects=True)
    assert "refreshed" in refreshed.text
    page = client.get("/ui/trackers")  # codes section lives on Trackers now
    assert "zenlesscodes.com" in page.text
    assert "Last checked" in page.text


def test_games_page_lists_status_and_refresh(client, ui_player, zzz_transport):
    client.app.state.llm_transport = zzz_transport
    page = client.get("/ui/games")
    assert "Zenless Zone Zero" in page.text and "Honkai: Star Rail" in page.text
    assert "Import catalog" in page.text and "Refresh codes" in page.text

    refreshed = client.post("/ui/games/zzz/refresh-catalog", follow_redirects=True)
    assert "catalog" in refreshed.text


def test_games_create_scaffolds_in_app(client, ui_player, monkeypatch):
    from game_companion.core.games import scaffold

    created = {}

    def fake_new(game_id, games_root):
        created["id"] = game_id
        return games_root / game_id

    def fake_register(game_id, games_root):
        created["registered"] = True

    monkeypatch.setattr(scaffold, "scaffold_new_game", fake_new)
    monkeypatch.setattr(scaffold, "register_installed", fake_register)

    ok = client.post(
        "/ui/games/create",
        data={"game_id": "Genshin", "display_name": "Genshin Impact"},
        follow_redirects=True,
    )
    assert "created" in ok.text
    assert created == {"id": "genshin", "registered": True}

    bad = client.post(
        "/ui/games/create",
        data={"game_id": "Bad Id!", "display_name": "X"},
        follow_redirects=True,
    )
    assert "2–30" in bad.text


# -- personas: role-as ------------------------------------------------------------------


def test_quick_character_persona_and_fragment(client, ui_player, zzz_transport):
    from game_companion.core.catalog.service import CatalogService
    from game_companion.core.games.registry import get_adapter
    from game_companion.core.persona.store import PersonaStore
    from game_companion.db.session import create_session_factory

    session = create_session_factory(client.app.state.engine)()
    CatalogService(session, get_adapter("zzz")).refresh("auto", transport=zzz_transport)
    session.commit()
    session.close()

    made = client.post(
        "/ui/personas/quick-character", data={"character_key": "alice"},
        follow_redirects=True,
    )
    assert "created" in made.text
    persona = PersonaStore(client.app.state.settings).get("as_alice")
    assert persona.role_as_character == "alice"
    assert persona.role_as_name == "Alice"
    fragment = persona.system_prompt_fragment()
    assert "role-playing as Alice" in fragment
    assert "never invents data" in fragment


# -- JSON API ----------------------------------------------------------------------------


def test_catalog_api_endpoints(client, zzz_transport):
    client.app.state.llm_transport = zzz_transport
    listed = client.get("/api/games/zzz/catalog").json()
    assert listed["entries"] == [] and listed["runs"] == []

    refreshed = client.post("/api/games/zzz/catalog/refresh").json()
    assert refreshed["summary"]["prydwen_characters"]["status"] == "ok"

    listed = client.get("/api/games/zzz/catalog?entity_type=character").json()
    assert len(listed["entries"]) == 2
    assert listed["entries"][0]["source"] == "prydwen"


# -- scheduler stays offline in tests -----------------------------------------------------


def test_auto_refresh_disabled_in_test_settings(settings):
    assert settings.auto_refresh is False


def test_refresh_prunes_runs_of_removed_sources(client, zzz_transport):
    """Run rows for sources the adapter no longer declares disappear."""
    from game_companion.core.catalog.service import CatalogService
    from game_companion.core.games.registry import get_adapter
    from game_companion.db.models import SourceRun
    from game_companion.db.session import create_session_factory

    session = create_session_factory(client.app.state.engine)()
    adapter = get_adapter("zzz")
    session.add(
        SourceRun(game_id="zzz", source_key="hakush_characters", kind="catalog",
                  status="error", detail="stale")
    )
    session.flush()
    CatalogService(session, adapter).refresh("auto", transport=zzz_transport)
    remaining = [r.source_key for r in CatalogService(session, adapter).runs()]
    assert "hakush_characters" not in remaining
    assert "prydwen_characters" in remaining
    session.close()
