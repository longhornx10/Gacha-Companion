"""Straggler-bug sweep: regression tests for the from-scratch audit fixes."""

from __future__ import annotations

# -- registry isolation: one broken adapter must not take down the app ----------


def test_broken_installed_adapter_is_skipped_not_fatal(client, tmp_path, monkeypatch):
    from game_companion.core.games import registry

    monkeypatch.setattr(registry, "_broken", {})
    registry.register("broken_game", "game_companion.games.does_not_exist.adapter:Nope")
    try:
        # unknown ids stay honest 404s …
        assert client.get("/api/games/broken_game/characters").status_code == 404
        # … but health/games/adapter lists keep working and skip the broken one
        health = client.get("/api/health").json()
        assert "broken_game" not in health["games"]
        assert health["status"] == "ok"
        assert "broken_game" not in client.get("/api/games").text
    finally:
        registry.register("broken_game", "")
        registry.register("broken_game", "game_companion.games.broken_game.adapter:Nope")
        with registry._lock:
            registry._extra.pop("broken_game", None)
            registry._broken.pop("broken_game", None)
            registry._instances.pop("broken_game", None)


def test_explicitly_requested_broken_adapter_errors_cleanly(client):
    from game_companion.core.games import registry

    registry.register("broken_game", "game_companion.games.does_not_exist.adapter:Nope")
    try:
        response = client.get("/api/games/broken_game")
        assert response.status_code in (400, 404)
        assert "installed but broken" in response.text
    finally:
        with registry._lock:
            registry._extra.pop("broken_game", None)
            registry._broken.pop("broken_game", None)
            registry._instances.pop("broken_game", None)


# -- /health carries the app version (stale-service detection) -----------------


def test_health_reports_app_version(client):
    from game_companion.app import APP_VERSION

    body = client.get("/health").json()
    assert body["version"] == APP_VERSION
    assert client.get("/api/health").json()["version"] == APP_VERSION


# -- llm model probe: key must never travel in the URL -------------------------


def test_models_probe_moves_key_out_of_query_string(client):
    client.app.state.llm_transport = None
    # GET with key in the query is gone: the access-log leak is closed
    assert client.get("/api/llm/models?key=sk-leaky").status_code == 405
    # POST with the key in the body probes normally (502: unreachable endpoint)
    response = client.post(
        "/api/llm/models",
        json={"llm_base_url": "https://example.com/v1", "llm_api_key": "sk-fine"},
    )
    assert response.status_code == 502


# -- persona hardening ---------------------------------------------------------


def test_persona_save_rejects_traversal_id(client, ui_player):
    response = client.post(
        "/ui/personas/save",
        data={
            "persona_id": "../../etc/pwned",
            "name": "Evil",
            "description": "",
            "tone": "friendly",
            "verbosity": "medium",
            "style_traits": "",
            "example_phrases": "",
            "system_preamble": "",
            "bound_game": "",
            "role_as_character": "",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "Could%20not%20save%20persona" in response.headers["location"]
    import pathlib

    assert not pathlib.Path("/etc/pwned.json").exists()


def test_persona_delete_ignores_traversal_id(client, tmp_path):
    bait = tmp_path / "bait.json"
    bait.write_text("{}", encoding="utf-8")
    from game_companion.config import Settings
    from game_companion.core.persona.store import PersonaStore

    store = PersonaStore(Settings(data_dir=str(tmp_path)))
    assert store.delete_file("../bait") is False
    assert bait.exists()


def test_persona_save_accepts_valid_id(client, ui_player):
    response = client.post(
        "/ui/personas/save",
        data={
            "persona_id": "my_test_persona",
            "name": "Test Persona",
            "description": "",
            "tone": "friendly",
            "verbosity": "medium",
            "style_traits": "",
            "example_phrases": "",
            "system_preamble": "",
            "bound_game": "",
            "role_as_character": "",
        },
        follow_redirects=True,
    )
    assert "saved" in response.text


# -- chat: a failed LLM turn keeps the user's message and the failure marker ---


def test_chat_failure_keeps_transcript(client, player):
    import re

    from game_companion.errors import LLMError

    class FailingLLM:
        configured = True

        def chat_with_tools(self, messages, tools=None):
            raise LLMError("endpoint down")

        def close(self):
            pass

    client.app.state.llm = FailingLLM()
    conv_page = client.post("/ui/chat/new", data={"persona_id": ""}, follow_redirects=True)
    match = re.search(r"c=([0-9a-f]+)", str(conv_page.url))
    assert match, conv_page.url
    conversation_id = match.group(1)

    page = client.post(
        f"/ui/chat/{conversation_id}/send", data={"text": "hello there"}, follow_redirects=True
    )
    assert "Chat error" in page.text
    # the transcript keeps BOTH the typed message and the failure marker
    assert "hello there" in page.text
    assert "chat failed: endpoint down" in page.text


def test_backup_retention_prunes_oldest(client, tmp_path, settings):
    from datetime import UTC, datetime

    from game_companion.core.backup import backups_dir, create_backup
    from game_companion.db.session import create_db_engine

    # a database must exist for backups to work
    engine = create_db_engine(settings.resolved_database_url)
    from game_companion.db.migrations.runner import upgrade_to_head

    upgrade_to_head(settings.resolved_database_url)
    engine.dispose()

    first = create_backup(settings)
    assert first.exists()
    # age the oldest one artificially, then create MAX_BACKUPS more
    for i in range(10):
        target = backups_dir(settings) / f"backup-2020010{i % 10}-00000{i}.zip"
        target.write_bytes(b"old")
        import os

        old = datetime(2020, 1, 1, tzinfo=UTC).timestamp()
        os.utime(target, (old, old))
    from game_companion.core.backup import MAX_BACKUPS, list_backups

    create_backup(settings)
    listed = list_backups(settings)
    assert len(listed) == MAX_BACKUPS
    # the just-created backup is kept; the stale 2020 ones are gone
    assert listed[0]["name"].startswith("backup-2")


def test_character_editor_can_clear_fields(client, player):
    from tests.conftest import make_character

    make_character(client, "zzz", "burnice", player_id=player, faction="Criminal")
    # the edit form posts faction empty → the field must actually be cleared
    page = client.post(
        "/ui/roster/burnice/edit",
        data={"display_name": "Burnice", "rarity": "", "level": "", "faction": ""},
        follow_redirects=True,
    )
    assert "saved" in page.text
    char = client.get("/api/games/zzz/characters/burnice").json()
    assert "faction" not in char["data"]
    assert char["last_verified_at"] is not None  # still counts as verified
