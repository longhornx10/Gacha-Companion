"""On-the-fly model handling + Database page (settings, model list, vision guard)."""

from __future__ import annotations

import json

import httpx


def _mock_models(models: list[str] | None = None, status: int = 200):
    payload = {"data": [{"id": m} for m in (models or [])]}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/models"):
            return httpx.Response(status, json=payload)
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    return httpx.MockTransport(handler)


def test_llm_status_reports_current_config(client):
    status = client.get("/api/llm/status").json()
    assert status["configured"] is False  # test env blanks the base URL
    assert status["model"] == "muse-glimmer-30b-vlm-128k"  # default
    assert status["vision_source"] == "auto"


def test_models_endpoint_probes_stored_endpoint(client):
    # a fresh install has no base URL: probing must fail honestly
    no_base = client.post("/api/llm/models")
    assert no_base.status_code == 502

    # once configured, the probe uses the stored endpoint + key
    client.put("/api/llm/config", json={"llm_base_url": "https://stored.example.com/v1"})
    client.app.state.llm_transport = _mock_models(["muse-glimmer-30b-vlm-128k", "vlrm-8b", "text-only-7b"])
    try:
        data = client.post("/api/llm/models").json()
    finally:
        client.app.state.llm_transport = None
    assert data["count"] == 3
    assert "vlrm-8b" in data["models"]


def test_models_endpoint_tests_new_endpoint_before_saving(client):
    client.app.state.llm_transport = _mock_models(["other-endpoint-model"])
    try:
        data = client.post("/api/llm/models", json={
            "llm_base_url": "https://example.com/v1", "llm_api_key": "sk-test",
        }).json()
    finally:
        client.app.state.llm_transport = None
    assert data["models"] == ["other-endpoint-model"]
    # nothing was saved
    assert client.get("/api/llm/status").json()["base_url"] == ""


def test_config_save_writes_env_and_hot_applies(client, settings):
    client.app.state.llm_transport = _mock_models(["new-vlm-model"])
    response = client.put("/api/llm/config", json={
        "llm_base_url": "https://new.example.com/v1",
        "llm_api_key": "sk-fresh-key-123",
        "llm_model": "new-vlm-model",
        "vision_override": "yes",
    })
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["applied_live"] is True
    assert body["status"]["configured"] is True
    assert body["status"]["base_url"] == "https://new.example.com/v1"
    assert body["status"]["vision_capable"] is True
    assert body["status"]["vision_source"] == "override"

    # the live client was swapped in place — chat now uses the new model
    assert client.app.state.llm.model == "new-vlm-model"
    assert client.app.state.llm.base_url == "https://new.example.com/v1"

    # .env actually contains the new values (and only managed keys touched)
    env_text = open(_env_path(), encoding="utf-8").read()
    assert "GAME_COMPANION_LLM_BASE_URL=https://new.example.com/v1" in env_text
    assert "GAME_COMPANION_LLM_VISION_MODEL=true" in env_text

    # vision override drop-back to auto removes the line
    client.put("/api/llm/config", json={"vision_override": "auto"})
    env_text = open(_env_path(), encoding="utf-8").read()
    assert "VISION_MODEL" not in env_text
    assert client.get("/api/llm/status").json()["vision_source"] == "auto"


def _env_path():
    from pathlib import Path

    return Path.cwd() / ".env"


def test_config_rejects_bad_values(client):
    bad_timeout = client.put("/api/llm/config", json={"llm_timeout_seconds": 1})
    assert bad_timeout.status_code == 422
    bad_override = client.put("/api/llm/config", json={"vision_override": "maybe"})
    assert bad_override.status_code == 422
    empty = client.put("/api/llm/config", json={})
    assert empty.status_code == 422


def test_models_endpoint_reports_endpoint_errors_honestly(client):
    client.put("/api/llm/config", json={"llm_base_url": "https://stored.example.com/v1"})
    client.app.state.llm_transport = _mock_models([], status=401)
    try:
        response = client.post("/api/llm/models")
    finally:
        client.app.state.llm_transport = None
    assert response.status_code == 502  # LLMError
    assert "401" in response.json()["detail"]["message"]


def test_vision_guard_blocks_non_vision_model_on_screenshots(client, ui_player):
    """A model that FAILS THE LIVE IMAGE PROBE is refused with a clear message;
    broker auto-routing that accepts images is never blocked."""
    import httpx as _httpx

    from tests.conftest import make_character

    make_character(client, "zzz", "burnice")
    # endpoint reachable, but refuses images (probe gets a 400). The seam must
    # be in place before the config PUT: that's when the client is rebuilt.
    calls = []

    def handler(request: _httpx.Request) -> _httpx.Response:
        calls.append(json.loads(request.content.decode()).get("model"))
        return _httpx.Response(400, json={"error": {"message": "model does not support images"}})

    client.app.state.llm_transport = _httpx.MockTransport(handler)
    client.put("/api/llm/config", json={
        "llm_base_url": "https://x.example.com/v1", "llm_model": "text-only-7b",
    })
    try:
        response = client.post("/api/games/zzz/imports", json={
            "screen_type": "character_overview",
            "image_base64": "aGVsbG8=",
            "character_hint": "burnice",
        })
    finally:
        client.app.state.llm_transport = None
    assert response.status_code == 422
    message = response.json()["detail"]["message"]
    assert "refused a test image" in message
    assert "Settings" in message  # tells the user where to fix it

    # auto-routing that DOES accept images (200 on the probe) is never blocked,
    # even though the model name matches nothing in the vision heuristic
    client.app.state.llm_transport = _httpx.MockTransport(
        lambda request: _httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})
    )
    client.put("/api/llm/config", json={"llm_model": "auto-router"})
    try:
        response2 = client.post("/api/games/zzz/imports", json={
            "screen_type": "character_overview",
            "image_base64": "aGVsbG8=",
            "character_hint": "burnice",
        })
    finally:
        client.app.state.llm_transport = None
    assert response2.status_code != 422  # proceeds to extraction


def test_imports_page_shows_vision_warning(client, ui_player):
    client.put("/api/llm/config", json={
        "llm_base_url": "https://x.example.com/v1", "llm_model": "text-only-7b",
    })
    page = client.get("/ui/imports")
    assert "auto-test it when you upload" in page.text
    client.put("/api/llm/config", json={"llm_model": "muse-glimmer-30b-vlm-128k"})
    page2 = client.get("/ui/imports")
    assert "auto-test it when you upload" not in page2.text


def test_settings_page_has_assistant_section(client, ui_player):
    page = client.get("/ui/settings")
    assert "Assistant model" in page.text
    assert "/api/llm/models" in page.text  # the auto-populating dropdown script
    assert "Reload list" in page.text
    assert "Test endpoint" in page.text
    assert "(saved — type only to replace)" in page.text or "not set" in page.text


def test_settings_assistant_form_saves_and_applies(client, ui_player):
    response = client.post("/ui/settings/assistant", data={
        "llm_base_url": "https://form.example.com/v1",
        "llm_model": "form-model-vlm",
        "llm_timeout_seconds": "90",
        "vision_override": "auto",
        "llm_api_key": "",
        "searxng_base_url": "",
    }, follow_redirects=True)
    assert response.status_code == 200
    assert "saved and applied" in response.text
    assert client.app.state.llm.model == "form-model-vlm"
    status = client.get("/api/llm/status").json()
    assert status["base_url"] == "https://form.example.com/v1"
    assert status["timeout_seconds"] == 90.0


def test_database_page_dropdown_and_detail(client, ui_player):

    from tests.conftest import make_zzz_roster

    make_zzz_roster(client, ui_player, ["burnice"])
    client.patch("/api/games/zzz/characters/burnice", json={
        "display_name": "Burnice White",
        "data": {"attribute": "fire", "specialty": "attack", "faction": "Sons of Calydon"},
    })
    page = client.get("/ui/roster/burnice/edit")
    assert page.status_code == 200
    text = page.text
    assert "Burnice White" in text  # roster meta names the display name
    assert "value=\"fire\" selected" in text  # attribute dropdown preselected from stored data
    assert "value=\"attack\" selected" in text
    assert "Sons of Calydon" in text  # faction editable
    assert "never verified" in text  # honesty: review prompt
    assert 'name="skill_basic_attack"' in text

    assert client.get("/ui/database", follow_redirects=False).headers["location"].startswith("/ui/games")


def test_database_page_save_updates_and_verifies(client, ui_player):
    from tests.conftest import make_character

    make_character(client, "zzz", "anby")
    saved = client.post("/ui/roster/anby/edit", data={
        "display_name": "Anby Demara",
        "rarity": "S",
        "level": "55",
        "duplication_level": "1",
        "owned": "on",
        "favorite": "on",
        "notes": "stun core",
        "attribute": "electric",
        "specialty": "stun",
        "faction": "Cunning Hares",
        "skill_basic_attack": "9",
    }, follow_redirects=True)
    assert "saved (verified today)" in saved.text

    char = client.get("/api/games/zzz/characters/anby").json()
    assert char["level"] == 55
    assert char["duplication_level"] == 1
    assert char["favorite"] is True
    assert char["data"] == {"attribute": "electric", "specialty": "stun", "faction": "Cunning Hares"}
    assert char["skills"]["basic_attack"] == 9
    assert char["last_verified_at"] is not None


def test_database_create_and_unknown_validation(client, ui_player):
    created = client.post("/ui/roster/create", data={
        "key": "Caelus Test", "display_name": "Caelus",
    }, follow_redirects=False)
    assert created.status_code == 303
    assert "caelus_test" in created.headers["location"]

    # adapter data validation still applies through the UI
    bad = client.post("/ui/roster/caelus_test/edit", data={
        "display_name": "Caelus", "attribute": "not-a-real-attribute",
    }, follow_redirects=True)
    assert "Save failed" in bad.text


def test_database_check_updates_and_approve_flow(client, ui_player, monkeypatch, settings):
    """'Check online sources' stages changes; the page lists and applies them."""

    # make bootstrap+check_sources offline-safe via the transport seam
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "1201": {"id": "1201", "name": "Brand New Agent", "rank": "S", "element": "Ether"},
        })

    client.app.state.llm_transport = httpx.MockTransport(handler)
    try:
        response = client.post("/ui/games/data/check-updates", follow_redirects=True)
    finally:
        client.app.state.llm_transport = None
    assert response.status_code == 200
    assert "Brand New Agent" in response.text  # appears in the pending table
    assert "new" in response.text

    changes = client.get("/api/games/zzz/changes?review_status=pending").json()["changes"]
    change_id = changes[0]["id"]
    approved = client.post(f"/ui/games/data/changes/{change_id}/approve", follow_redirects=True)
    assert "approved" in approved.text.lower()
