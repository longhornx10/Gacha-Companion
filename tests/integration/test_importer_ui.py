"""M21: deterministic roster importer, gear families/type, inline edit UI."""

from __future__ import annotations

import sys
from pathlib import Path

ROSTER_TEXT = """PHOENIX ROSTER ZZZ
Burnice lv60 M1
Ellen level 60, M2
lycaon lv 42
Anby M0
totally-not-an-agent lv50 M3
"""


def _stage(client, player: str, text: str = ROSTER_TEXT) -> dict:
    return client.post(
        f"/api/games/zzz/import-roster?player_id={player}", json={"text": text}
    )


def test_parse_stage_and_confirm_roundtrip(client, player):
    staged = _stage(client, player)
    assert staged.status_code == 200, staged.text
    data = staged.json()
    assert data["entries"] == 4
    assert data["changes"] == 4  # four creates
    assert data["status"] == "pending"
    reasons = " ".join(u["reason"] for u in data["unresolved"])
    assert "not in game data" in reasons  # unknown name reported, not guessed
    assert data["changes_detail"][0]["action"] == "create"

    import_id = None
    listing = client.get(f"/api/games/zzz/imports?player_id={player}").json()["imports"]
    import_id = [i for i in listing if i["screen_type"] == "roster_txt"][0]["id"]

    confirmed = client.post(f"/api/games/zzz/imports/{import_id}/confirm?player_id={player}")
    assert confirmed.status_code == 200, confirmed.text

    roster = client.get(f"/api/games/zzz/characters?player_id={player}").json()["characters"]
    by_key = {c["key"]: c for c in roster}
    assert set(by_key) == {"burnice", "ellen", "lycaon", "anby"}
    assert by_key["burnice"]["level"] == 60
    assert by_key["burnice"]["duplication_level"] == 1
    assert by_key["ellen"]["duplication_level"] == 2
    assert by_key["lycaon"]["level"] == 42
    assert by_key["anby"]["level"] is None  # absent fields stay null, honestly
    assert by_key["burnice"]["source"] == "roster_import"


def test_stage_rejects_empty_and_confirm_twice(client, player):
    empty = client.post(
        f"/api/games/zzz/import-roster?player_id={player}", json={"text": "# nothing here"}
    )
    assert empty.status_code == 422

    staged = _stage(client, player)
    assert staged.status_code == 200
    listing = client.get(f"/api/games/zzz/imports?player_id={player}").json()["imports"]
    import_id = [i for i in listing if i["screen_type"] == "roster_txt"][0]["id"]
    assert client.post(f"/api/games/zzz/imports/{import_id}/confirm?player_id={player}").status_code == 200
    again = client.post(f"/api/games/zzz/imports/{import_id}/confirm?player_id={player}")
    assert again.status_code == 422


def test_roster_import_updates_existing_characters(client, player):
    from tests.conftest import make_character

    make_character(client, "zzz", "burnice", level=1)
    staged = _stage(client, player, "Burnice lv60 M2\n")
    assert staged.status_code == 200
    data = staged.json()
    assert data["changes"] == 2
    actions = {(c["field"], c["current"], c["proposed"]) for c in data["changes_detail"]}
    assert ("level", 1, 60) in actions
    assert ("duplication_level", None, 2) in actions


def test_import_via_ui_flow(client, ui_player):
    response = client.post(
        "/ui/imports/roster-txt",
        data={"text": "Burnice lv60 M1\n"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "review below" in response.text or "Staged" in response.text

    page = client.get("/ui/imports")
    assert page.status_code == 200
    assert "roster txt" in page.text
    assert "Apply" in page.text

    # find the pending import and confirm it through the UI
    imports = client.get("/api/games/zzz/imports").json()["imports"]
    import_id = [i for i in imports if i["status"] == "pending"][0]["id"]
    done = client.post(f"/ui/imports/{import_id}/confirm", follow_redirects=True)
    assert done.status_code == 200
    assert "Burnice" in client.get("/ui/roster").text


def test_screenshot_upload_without_llm_fails_gracefully(client, ui_player):
    response = client.post(
        "/ui/imports/upload",
        data={"screen_type": "character_overview", "character_hint": "burnice"},
        files={"upload": ("burnice.png", b"fake-png-bytes", "image/png")},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "failed" in response.text.lower()


def test_gear_type_defaults_and_validation(client, player):
    from game_companion.core.games.registry import get_adapter

    families = get_adapter("zzz").gear_families()
    assert families and families[0].key == "disc"
    assert families[0].set_rule == "fixed_pieces"
    assert [s.key for s in families[0].slots] == ["1", "2", "3", "4", "5", "6"]

    created = client.post(
        f"/api/games/zzz/gear?player_id={player}",
        json={"set_key": "shadow_harmony", "slot": "1"},
    ).json()
    assert created["gear_type"] == "disc"  # adapter default family

    bad = client.post(
        f"/api/games/zzz/gear?player_id={player}",
        json={"gear_type": "relic", "slot": "1"},
    )
    assert bad.status_code == 422


def test_inline_character_edit_via_ui(client, ui_player):
    from tests.conftest import make_character

    make_character(client, "zzz", "burnice")
    page = client.get("/ui/roster/burnice/edit")
    assert page.status_code == 200
    assert "Burnice" in page.text

    saved = client.post(
        "/ui/roster/burnice/edit",
        data={"level": "60", "duplication_level": "2", "favorite": "on",
              "notes": "main dps", "skill_basic_attack": "7"},
        follow_redirects=True,
    )
    assert saved.status_code == 200
    assert "saved" in saved.text

    char = client.get("/api/games/zzz/characters/burnice").json()
    assert char["level"] == 60
    assert char["duplication_level"] == 2
    assert char["favorite"] is True
    assert char["notes"] == "main dps"
    assert char["skills"]["basic_attack"] == 7
    assert char["last_verified_at"] is not None  # user statement = verification


def test_resource_and_code_inline_actions(client, ui_player):
    set_resource = client.post(
        "/ui/resources/update", data={"resource_key": "polychrome", "quantity": "12500"},
        follow_redirects=True,
    )
    assert "12,500".replace(",", "") in set_resource.text
    resources = client.get("/api/games/zzz/resources").json()["resources"]
    poly = [r for r in resources if r["resource_key"] == "polychrome"][0]
    assert poly["quantity"] == 12500

    # codes are no longer added by hand: the UI refreshes them from the
    # game's auto source (mocked here via the app's transport seam)
    import httpx as _httpx

    payload = {
        "codes": [
            {"code": "zzzfree100", "rewards": "Polychrome ×50", "status": "active",
             "discovered_date": "2026-09-01"},
        ],
        "expired": [{"code": "oldone", "status": "expired"}],
    }
    transport = _httpx.MockTransport(
        lambda request: _httpx.Response(200, json=payload)
    )
    client.app.state.llm_transport = transport
    refreshed = client.post("/ui/codes/refresh", follow_redirects=True)
    assert "refreshed" in refreshed.text  # lands on /ui/trackers#codes
    codes = client.get("/api/games/zzz/codes").json()["codes"]
    assert {c["code"] for c in codes} == {"zzzfree100", "oldone"}
    code_id = [c for c in codes if c["code"] == "zzzfree100"][0]["id"]
    toggled = client.post(f"/ui/codes/{code_id}/toggle-used", follow_redirects=True)
    assert toggled.status_code == 200
    assert client.get("/api/games/zzz/codes").json()["codes"][0]["used"] is True


def test_team_activation_via_ui(client, ui_player):
    from tests.conftest import make_zzz_roster

    make_zzz_roster(client, ui_player, ["burnice", "ellen", "lycaon", "anby"])
    for name, members in (("Alpha", ["burnice", "ellen", "lycaon"]), ("Beta", ["anby", "ellen", "lycaon"])):
        created = client.post(
            "/api/games/zzz/teams",
            json={"name": name, "members": [{"character": m} for m in members]},
        )
        assert created.status_code == 201, created.text
    teams = {t["name"]: t for t in client.get("/api/games/zzz/teams").json()["teams"]}
    alpha_id = teams["Alpha"]["id"]

    activated = client.post(f"/ui/teams/{alpha_id}/activate", follow_redirects=True)
    assert activated.status_code == 200
    assert "active" in client.get("/ui/teams").text

    deactivated = client.post(f"/ui/teams/{alpha_id}/deactivate", follow_redirects=True)
    assert deactivated.status_code == 200
    teams_after = {t["name"]: t for t in client.get("/api/games/zzz/teams").json()["teams"]}
    assert teams_after["Alpha"]["is_active"] is False


def test_cli_import_roster_yes(tmp_path, monkeypatch, settings):
    """End-to-end CLI: stage + apply in one shot against a fresh data dir."""
    import json
    import subprocess

    from game_companion.db.migrations.runner import upgrade_to_head
    from game_companion.db.session import create_db_engine, create_session_factory

    upgrade_to_head()
    engine = create_db_engine(settings.resolved_database_url)
    session = create_session_factory(engine)()
    from game_companion.db.models import PlayerProfile
    from game_companion.db.repositories import PlayerRepository

    PlayerRepository(session).add(PlayerProfile(display_name="CLI Player"))
    session.commit()
    session.close()
    engine.dispose()

    roster_file = tmp_path / "roster.txt"
    roster_file.write_text("Burnice lv60 M1\n", encoding="utf-8")

    result = subprocess.run(
        [
            # the venv's own entry point — no `uv run`, which resolves
            # project-relative and breaks under the fixture's tmp CWD
            str(Path(sys.executable).parent / "game-companion"), "import-roster",
            "--game", "zzz", "--file", str(roster_file), "--yes",
        ],
        capture_output=True, text=True,
        env={**__import__("os").environ, "GAME_COMPANION_DATA_DIR": str(settings.resolved_data_dir)},
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    decoder = json.JSONDecoder()
    idx = result.stdout.index("{")
    payload = {}
    while idx != -1:
        obj, end = decoder.raw_decode(result.stdout[idx:])
        payload = obj  # keep decoding — the last JSON object is the final result
        nxt = result.stdout.find("{", idx + end)
        idx = nxt if nxt != -1 else -1
    assert payload["applied"]


def test_migration_added_gear_type(client, settings):
    """gear_type exists, is NOT NULL, and defaults existing rows to 'disc'."""
    from sqlalchemy import inspect

    from game_companion.db.session import create_db_engine

    engine = create_db_engine(settings.resolved_database_url)
    cols = {c["name"]: c for c in inspect(engine).get_columns("gear_items")}
    engine.dispose()
    assert "gear_type" in cols
    assert cols["gear_type"]["nullable"] is False
    assert "disc" in str(cols["gear_type"].get("default"))
