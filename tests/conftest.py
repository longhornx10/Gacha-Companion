"""Shared fixtures: isolated data dir, migrated DB, API client, players."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def settings(tmp_path: Path, monkeypatch):
    # hot-applied settings write os.environ (pydantic precedence) — clear any
    # leaked GAME_COMPANION_* vars so every test starts from a clean slate
    # (monkeypatch restores whatever was there after the test).
    import os

    for var in [k for k in os.environ if k.startswith("GAME_COMPANION_")]:
        monkeypatch.delenv(var, raising=False)
    # ISOLATE THE CWD: .env is resolved relative to the process CWD (pydantic
    # env_file + core/appsettings writes) — tests must never touch the real
    # repo .env. chdir into the per-test tmp dir; monkeypatch restores it.
    monkeypatch.chdir(tmp_path)
    data_dir = tmp_path / "data"
    monkeypatch.setenv("GAME_COMPANION_DATA_DIR", str(data_dir))
    monkeypatch.setenv("ALEMBIC_DATABASE_URL", f"sqlite:///{data_dir / 'test.db'}")
    # keep the suite fully offline: no LLM endpoint, no search provider,
    # no background auto-refresh network fetches
    monkeypatch.setenv("GAME_COMPANION_LLM_BASE_URL", "")
    monkeypatch.setenv("GAME_COMPANION_AUTO_REFRESH", "0")
    monkeypatch.delenv("GAME_COMPANION_LLM_API_KEY", raising=False)
    monkeypatch.delenv("GAME_COMPANION_SEARXNG_BASE_URL", raising=False)
    from game_companion.config import get_settings

    get_settings.cache_clear()
    return get_settings()


@pytest.fixture()
def client(settings):
    from game_companion.app import create_app
    from game_companion.db.migrations.runner import upgrade_to_head

    upgrade_to_head()
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def player(client) -> str:
    response = client.post("/api/players", json={"display_name": "Test Player"})
    assert response.status_code == 201, response.text
    return response.json()["id"]


@pytest.fixture()
def ui_player(client) -> str:
    """A player created through the /ui first-run form; returns the player id."""
    response = client.post(
        "/ui/players/create", data={"display_name": "Phoenix"}, follow_redirects=False
    )
    assert response.status_code == 303, response.text
    players = client.get("/api/players").json()["players"]
    return players[-1]["id"]


@pytest.fixture()
def second_player(client) -> str:
    response = client.post("/api/players", json={"display_name": "Second Player"})
    assert response.status_code == 201
    return response.json()["id"]


def make_character(client, game_id: str, key: str, player_id: str | None = None, **fields) -> dict:
    payload = {"key": key, **fields}
    url = f"/api/games/{game_id}/characters"
    if player_id:
        url += f"?player_id={player_id}"
    response = client.post(url, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def make_zzz_roster(client, player: str, keys: list[str]) -> list[dict]:
    from game_companion.core.games.registry import get_adapter

    adapter = get_adapter("zzz")
    out = []
    for key in keys:
        meta = adapter.character_meta(key) or {}
        out.append(
            make_character(
                client,
                "zzz",
                key,
                level=60,
                data={
                    "attribute": meta.get("attribute"),
                    "specialty": meta.get("specialty"),
                    "faction": meta.get("faction"),
                },
            )
        )
    return out


class MockLLM:
    """Deterministic LLM double for tutor/research/vision tests."""

    def __init__(self, complete_text: str = "MOCK EXPLANATION", extraction: dict | None = None):
        self.configured = True
        self.complete_text = complete_text
        self.extraction = extraction or {}
        self.calls: list[dict] = []

    def complete(self, messages, *, temperature: float = 0.4, **kwargs) -> str:
        self.calls.append({"messages": messages, "temperature": temperature})
        return self.complete_text

    def extract_structured(self, schema, instruction, *, images=(), context="", temperature=0.0, retries=1):
        self.calls.append({"instruction": instruction, "images": len(list(images))})
        if not self.extraction and hasattr(schema, "model_construct"):
            return schema.model_construct()
        return schema.model_validate(self.extraction)

    def close(self) -> None:  # match LLMClient's teardown contract
        pass
