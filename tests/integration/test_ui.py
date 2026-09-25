"""M20: web UI pages, game switcher, dashboard aggregate, backup/restore."""

from __future__ import annotations


def _seed_zzz_world(client, player: str) -> dict:
    from tests.conftest import make_zzz_roster

    roster = make_zzz_roster(client, player, ["burnice", "ellen", "lycaon"])
    client.put(f"/api/games/zzz/resources/polychrome?player_id={player}", json={"quantity": 12000})
    client.post(f"/api/games/zzz/codes?player_id={player}", json={"code": "ZZZFREE100"})
    client.post(
        f"/api/games/zzz/teams?player_id={player}",
        json={
            "name": "Fire team",
            "members": [{"character": "burnice"}, {"character": "ellen"}, {"character": "lycaon"}],
            "is_active": True,
        },
    )
    client.post(
        f"/api/games/zzz/combat-results?player_id={player}",
        json={"encounter_key": "shiyu_defense", "cleared": True, "stars": 3},
    )
    equip = client.post(
        f"/api/games/zzz/equipment?player_id={player}",
        json={"key": "rainforest_gourmet", "display_name": "Rainforest Gourmet", "rarity": "S"},
    ).json()
    gear = client.post(
        f"/api/games/zzz/gear?player_id={player}",
        json={"set_key": "woodpecker_electro", "slot": "4", "rarity": "S", "level": 15,
              "main_stat_key": "crit_rate", "main_stat_value": 24.0, "substats": []},
    ).json()
    return {"roster": roster, "equip": equip, "gear": gear}


def test_setup_page_when_no_players(client):
    response = client.get("/ui")
    assert response.status_code == 200
    assert "Welcome" in response.text
    assert "profile" in response.text.lower()


def test_first_run_creates_profile_and_shows_empty_dashboard(client, ui_player):
    dashboard = client.get("/ui")
    assert dashboard.status_code == 200
    assert "Zenless Zone Zero" in dashboard.text
    assert "0" in dashboard.text  # empty counts render


def test_all_pages_render_seeded_world(client, player):
    _seed_zzz_world(client, player)
    pages = {
        "/ui": ["Zenless Zone Zero", "Agents", "12,000".replace(",", ""), "Fire team", "Achievements"],
        "/ui/roster": ["Burnice", "Ellen"],
        "/ui/teams": ["Fire team", "active"],
        "/ui/gear": ["Rainforest Gourmet", "woodpecker_electro"],
        "/ui/trackers": ["Polychrome", "ZZZFREE100", "shiyu defense"],
        "/ui/settings": ["Test Player", "Backups", "Zenless Zone Zero"],
    }
    for path, needles in pages.items():
        response = client.get(path)
        assert response.status_code == 200, path
        for needle in needles:
            assert needle in response.text, f"{path} missing {needle!r}"


def test_pages_redirect_to_setup_without_player(client):
    # settings is intentionally reachable without a profile (it offers profile creation)
    for path in ("/ui/roster", "/ui/teams", "/ui/gear", "/ui/resources", "/ui/codes", "/ui/history", "/ui/trackers"):
        response = client.get(path, follow_redirects=False)
        assert response.status_code == 303, path
        assert response.headers["location"] == "/ui"
    settings = client.get("/ui/settings")
    assert settings.status_code == 200
    assert "Create profile" in settings.text


def test_audit_page_lists_findings(client, player):
    from tests.conftest import make_character

    make_character(client, "zzz", "burnice")
    response = client.get("/ui/audit")
    assert response.status_code == 200
    assert "Burnice" in response.text
    assert "never verified" in response.text


def test_switch_game_rethemes_and_rescopes(client, player):
    from tests.conftest import make_character

    make_character(client, "zzz", "burnice")
    make_character(client, "example", "aria")

    zzz_page = client.get("/ui/roster")
    assert "#ed343e" in zzz_page.text  # ZZZ signature red (game menu accent)
    assert "Burnice" in zzz_page.text

    switch = client.post("/ui/select-game", data={"game_id": "example", "next": "/ui/roster"},
                         follow_redirects=False)
    assert switch.status_code == 303

    example_page = client.get("/ui/roster")
    assert "#8b93ff" in example_page.text  # example game keeps the default theme
    assert "Aria" in example_page.text
    assert "Burnice" not in example_page.text  # game isolation carries into the UI

    client.post("/ui/select-game", data={"game_id": "zzz"})
    assert "Burnice" in client.get("/ui/roster").text


def test_switch_game_rejects_unknown(client, player):
    response = client.post("/ui/select-game", data={"game_id": "nope"}, follow_redirects=True)
    assert response.status_code == 200
    assert "Unknown game" in response.text


def test_dashboard_api_aggregate(client, player):
    _seed_zzz_world(client, player)
    data = client.get(f"/api/dashboard?game_id=zzz&player_id={player}").json()
    assert data["game_id"] == "zzz"
    assert data["roster_count"] == 3
    assert data["gear_count"] == 1
    assert data["equipment_count"] == 1
    assert data["codes_active"] == 1
    assert data["active_team"]["name"] == "Fire team"
    assert len(data["active_team"]["members"]) == 3
    assert any(r["resource_key"] == "polychrome" for r in data["resources"])
    assert data["recent_results"] and data["recent_results"][0]["cleared"] is True
    assert data["last_import"] is None


def test_backup_and_restore_roundtrip(client, player):
    from tests.conftest import make_character

    make_character(client, "zzz", "burnice")
    backup = client.post("/api/system/backup")
    assert backup.status_code == 201, backup.text
    name = backup.json()["name"]
    assert name.startswith("backup-")

    listing = client.get("/api/system/backups").json()["backups"]
    assert [b["name"] for b in listing] == [name]

    # mutate after the backup
    make_character(client, "zzz", "ellen")
    keys_before = {c["key"] for c in client.get(f"/api/games/zzz/characters?player_id={player}").json()["characters"]}
    assert keys_before == {"burnice", "ellen"}

    restored = client.post("/api/system/restore", json={"name": name})
    assert restored.status_code == 200, restored.text

    keys_after = {c["key"] for c in client.get(f"/api/games/zzz/characters?player_id={player}").json()["characters"]}
    assert keys_after == {"burnice"}, "restore must roll the DB back to the backup"

    # the service keeps working after the engine swap
    make_character(client, "zzz", "lycaon")
    assert "Lycaon" in client.get("/ui/roster").text


def test_restore_via_settings_ui(client, player):
    from tests.conftest import make_character

    make_character(client, "zzz", "burnice")
    name = client.post("/api/system/backup").json()["name"]
    make_character(client, "zzz", "ellen")

    response = client.post("/ui/restore", data={"name": name}, follow_redirects=True)
    assert response.status_code == 200
    assert "Restored" in response.text
    keys = {c["key"] for c in client.get(f"/api/games/zzz/characters?player_id={player}").json()["characters"]}
    assert keys == {"burnice"}


def test_restore_rejects_bad_names(client):
    for bad in ("../evil.zip", "not-a-backup", "backup-999999-999999.zip"):
        response = client.post("/api/system/restore", json={"name": bad})
        assert response.status_code in (404, 422), bad


def test_data_dir_endpoint(client):
    data = client.get("/api/system/data-dir").json()
    assert data["data_dir"].endswith("data")


def test_serve_refuses_non_loopback_without_expose(monkeypatch, settings):
    import argparse

    from game_companion import cli

    monkeypatch.delenv("GAME_COMPANION_EXPOSE", raising=False)
    from game_companion.config import get_settings

    get_settings.cache_clear()
    args = argparse.Namespace(host="0.0.0.0", port=None)
    assert cli._cmd_serve(args) == 2  # refuses, does not start uvicorn

    monkeypatch.setenv("GAME_COMPANION_EXPOSE", "1")
    get_settings.cache_clear()


def test_health_and_root_unchanged(client):
    assert client.get("/health").json()["status"] == "ok"
    response = client.get("/ui/static/style.css")
    assert response.status_code == 200
    assert "--accent" in response.text
    htmx = client.get("/ui/static/htmx.min.js")
    assert htmx.status_code == 200
    assert "htmx" in htmx.text


def test_example_game_hidden_from_every_listing(client, player):
    """The genericity example stays reachable for tests but is never offered."""
    picker = client.get("/ui")
    assert "Aether Tactics" not in picker.text
    assert "Aether Tactics" not in client.get("/ui/games").text
    health = client.get("/api/health").json()
    assert "example" not in health["games"] and "zzz" in health["games"]
    api_games = client.get("/api/games").json()["games"]
    assert {g["game_id"] for g in api_games} == {"zzz", "hsr", "nte"}
    # data access still works directly (tests rely on it)
    assert client.get("/api/games/example/characters").status_code == 200
