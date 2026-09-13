"""Research layer (M6) and change monitoring (M19)."""

import pytest


@pytest.fixture()
def seeded(client):
    response = client.post("/api/games/zzz/sources", json={"seed_defaults": True})
    assert response.status_code == 201
    return {s["key"]: s for s in response.json()["seeded"]}


def test_seed_sources_from_adapter_registry(client, seeded):
    assert "zzz_official_site" in seeded
    assert seeded["zzz_official_site"]["trust"] == 5
    # idempotent
    client.post("/api/games/zzz/sources", json={"seed_defaults": True})


def test_claims_carry_type_and_evidence_and_cross_check(client, seeded):
    client.post("/api/games/zzz/claims", json={
        "subject": "burnice",
        "claim_type": "build_recommendation",
        "content": "4pc Fanged Metal preferred",
        "source_key": "prydwen_zzz",
        "confidence": 0.8,
    })
    client.post("/api/games/zzz/claims", json={
        "subject": "burnice",
        "claim_type": "build_recommendation",
        "content": "4pc Inferno Metal preferred",
        "source_key": "game8_zzz",
    })

    claims = client.get("/api/games/zzz/claims?subject=burnice").json()["claims"]
    assert len(claims) == 2
    assert claims[0]["evidence"] == []

    cross = client.get("/api/games/zzz/claims/cross-check/burnice").json()
    assert cross["disagreements"], "differing sources must not be reported as consensus"
    assert "no consensus claimed" in cross["disagreements"][0]["detail"]

    # invalid claim type rejected
    bad = client.post("/api/games/zzz/claims", json={
        "subject": "x", "claim_type": "absolute_truth", "content": "..."})
    assert bad.status_code == 422


def test_change_review_workflow(client, seeded, monkeypatch):
    from game_companion.core.research import service as research_service

    calls = {"count": 0}

    def fake_fetch(url, max_chars=20000):
        calls["count"] += 1
        return f"page content v{calls['count']}"

    monkeypatch.setattr(research_service, "fetch_text", fake_fetch)

    first = client.post("/api/games/zzz/changes/check-sources").json()
    assert first["checked"] >= 1
    assert not any(r.get("changed") for r in first["results"])

    second = client.post("/api/games/zzz/changes/check-sources").json()
    assert any(r.get("changed") for r in second["results"])

    changes = client.get("/api/games/zzz/changes?review_status=pending").json()["changes"]
    assert changes, "content change must create a pending record"

    approved = client.post(f"/api/games/zzz/changes/{changes[0]['id']}/approve").json()
    assert approved["review_status"] == "approved"

    double = client.post(f"/api/games/zzz/changes/{changes[0]['id']}/approve")
    assert double.status_code == 422  # already reviewed


def test_research_query_requires_search_provider(client, player):
    response = client.post("/api/games/zzz/research/query", json={"question": "best Burnice teams?"})
    assert response.status_code == 503  # no SearXNG configured: fail loud, not silent


def test_example_game_has_its_own_source_registry(client):
    seeded = client.post("/api/games/example/sources", json={"seed_defaults": True}).json()["seeded"]
    assert seeded[0]["key"] == "example_wiki"
