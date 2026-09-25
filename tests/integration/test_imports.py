"""Screenshot import flow (M5): pending -> confirm/reject, never silent writes."""

import base64

from tests.conftest import MockLLM, make_character


def test_manual_candidate_confirm_flow(client, player):
    char = make_character(client, "zzz", "burnice", level=1)

    created = client.post("/api/games/zzz/imports", json={
        "screen_type": "character_overview",
        "candidate": {"character_name": "Burnice White", "level": 60, "duplication_level": 2},
        "character_hint": "burnice",
    }).json()
    assert created["status"] == "pending"
    assert "level" in created["extracted_fields"]
    assert created["diff"]["changes"], "diff must show proposed changes"

    # nothing applied yet
    unchanged = client.get("/api/games/zzz/characters/burnice").json()
    assert unchanged["level"] == 1

    confirmed = client.post(f"/api/games/zzz/imports/{created['import_id']}/confirm").json()
    assert confirmed["status"] == "applied"
    assert "verified" in confirmed["applied"][0]

    updated = client.get("/api/games/zzz/characters/burnice").json()
    assert updated["level"] == 60
    assert updated["duplication_level"] == 2
    assert updated["source"] == "screenshot_import"  # source reflects the data pathway
    assert updated["last_verified_at"] is not None
    assert char["id"] == updated["id"]


def test_reject_flow(client, player):
    make_character(client, "zzz", "ellen")
    created = client.post("/api/games/zzz/imports", json={
        "screen_type": "character_overview",
        "candidate": {"character_name": "Ellen Joe", "level": 60},
    }).json()
    rejected = client.post(f"/api/games/zzz/imports/{created['import_id']}/reject").json()
    assert rejected["status"] == "rejected"
    assert client.get("/api/games/zzz/characters/ellen").json()["level"] is None
    again = client.post(f"/api/games/zzz/imports/{created['import_id']}/confirm")
    assert again.status_code == 422


def test_invalid_candidate_rejected_by_schema(client, player):
    response = client.post("/api/games/zzz/imports", json={
        "screen_type": "character_overview",
        "candidate": {"level": 1000},
    })
    assert response.status_code == 422


def test_drive_disc_detail_import_creates_gear(client, player):
    make_character(client, "zzz", "burnice")
    created = client.post("/api/games/zzz/imports", json={
        "screen_type": "gear_detail",
        "candidate": {
            "slot": "5", "set_key": "fanged_metal", "rarity": "S", "level": 15,
            "main_stat_key": "crit_rate", "main_stat_value": 24.0,
            "substats": [{"key": "crit_dmg", "value": 40.0, "rolls": 4}],
        },
        "character_hint": "burnice",
    }).json()
    confirmed = client.post(f"/api/games/zzz/imports/{created['import_id']}/confirm").json()
    assert "gear item" in confirmed["applied"][0]
    gear = client.get("/api/games/zzz/gear?character=burnice").json()["gear"]
    assert gear[0]["main_stat_key"] == "crit_rate"
    assert gear[0]["substats"][0]["rolls"] == 4


def test_disc_loadout_screen_is_informational_only(client, player):
    created = client.post("/api/games/zzz/imports", json={
        "screen_type": "gear_list",
        "candidate": {"discs": [{"slot": "1", "set_name": "Woodpecker Electro"}]},
    }).json()
    response = client.post(f"/api/games/zzz/imports/{created['import_id']}/confirm")
    assert response.status_code == 422  # requires per-disc confirmation


def test_vlm_extraction_uses_configured_llm(client, player, monkeypatch):
    make_character(client, "zzz", "burnice")
    mock_llm = MockLLM(extraction={
        "character_name": "Burnice White", "level": 60, "mindscape": 0,
        "extraction_confidence": 0.9,
    })
    monkeypatch.setattr(client.app.state, "llm", mock_llm, raising=False)

    png = base64.b64encode(b"\x89PNG fake image bytes").decode()
    created = client.post("/api/games/zzz/imports", json={
        "screen_type": "character_overview",
        "image_base64": png,
        "screenshot_name": "burnice.png",
        "character_hint": "burnice",
    }).json()
    assert created["status"] == "pending"
    assert created["confidence"] == 0.9
    assert mock_llm.calls[0]["images"] == 1

    client.post(f"/api/games/zzz/imports/{created['import_id']}/confirm")
    assert client.get("/api/games/zzz/characters/burnice").json()["level"] == 60


def test_failed_extraction_recorded_not_applied(client, player, monkeypatch):
    class FailingLLM(MockLLM):
        def extract_structured(self, *args, **kwargs):
            from pydantic import BaseModel

            class Bogus(BaseModel):
                level: int

            Bogus.model_validate({})  # raises ValidationError

    monkeypatch.setattr(client.app.state, "llm", FailingLLM(), raising=False)
    created = client.post("/api/games/zzz/imports", json={
        "screen_type": "character_overview", "image_base64": base64.b64encode(b"x").decode(),
    }).json()
    assert created["status"] == "failed"
    assert created["error"]
