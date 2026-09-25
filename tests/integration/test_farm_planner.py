"""M26 farm planner over the API and web UI."""

from __future__ import annotations


def _add_disc(client, player: str, **overrides) -> dict:
    payload = {
        "set_key": "woodpecker_electro",
        "slot": "4",
        "rarity": "S",
        "level": 15,
        "main_stat_key": "crit_rate",
        "main_stat_value": 24.0,
        "substats": [],
    }
    payload.update(overrides)
    return client.post(f"/api/games/zzz/gear?player_id={player}", json=payload).json()


def test_zzz_farm_plan_api_available(client, player):
    _add_disc(client, player)
    response = client.get(f"/api/games/zzz/farm-plan?player_id={player}&beta=1.2")
    assert response.status_code == 200
    data = response.json()
    assert data["available"] is True
    assert data["set_rows"], "meta sets should be ranked"
    by_key = {r["set_key"]: r for r in data["set_rows"]}
    # the maxed S-rank crit disc gives Woodpecker full coverage on β target ≥ 1
    assert by_key["woodpecker_electro"]["effective"] > 0
    assert by_key["woodpecker_electro"]["coverage"] > 0
    assert data["stage_rows"]
    assert data["labels"]["demand"] == "CURRENT BUILD DATA"
    assert data["provenance"]["grading"]["label"] == "HEURISTIC"
    assert len(data["stage_index"]) == 12


def test_farm_plan_without_inventory_is_all_uncovered(client, player):
    data = client.get(f"/api/games/zzz/farm-plan?player_id={player}").json()
    assert data["available"] is True
    assert all(r["coverage"] in (0.0, None) for r in data["set_rows"])
    assert any(r["coverage"] == 0.0 for r in data["set_rows"])
    assert data["inventory_summary"]["discs"] == 0


def test_hsr_farm_plan_reports_unavailable(client, player):
    response = client.get(f"/api/games/hsr/farm-plan?player_id={player}")
    assert response.status_code == 200
    data = response.json()
    assert data["available"] is False
    assert "no meta dataset" in data["detail"]


def test_ui_farm_page_renders_plan(client, player):
    _add_disc(client, player)
    response = client.get("/ui/farm")
    assert response.status_code == 200
    assert "Farm Plan" in response.text
    assert "Farm this next" in response.text
    assert "How you're doing" in response.text
    assert "Other stages worth running" in response.text
    # the technical detail fold still carries labels + provenance
    assert "Show the details" in response.text
    assert "CURRENT BUILD DATA" in response.text
    assert "Prydwen" in response.text
    assert "3.2" in response.text


def test_ui_farm_page_default_controls(client, player):
    page = client.get("/ui/farm").text
    assert '<option value="mine" selected>My agents</option>' in page
    assert '<option value="comfortable" selected>A comfortable margin</option>' in page


def test_ui_farm_page_control_selections(client, player):
    page = client.get("/ui/farm?scope=meta&spare=lots")
    assert page.status_code == 200
    flat = " ".join(page.text.split())
    assert '<option value="meta" selected>Everyone in the meta</option>' in flat
    assert '<option value="lots" selected>Lots of spares</option>' in flat


def test_ui_farm_page_roster_scope(client, player):
    # no agents yet: default "My agents" scope falls back and says so
    empty = client.get("/ui/farm").text
    assert "None of your saved agents are in the current meta dataset yet" in empty
    # own a meta agent (Burnice): fallback note disappears, her sets drive the plan
    created = client.post(f"/api/games/zzz/characters?player_id={player}", json={"key": "burnice"})
    assert created.status_code in (200, 201), created.text
    owned = client.get("/ui/farm").text
    assert "None of your saved agents" not in owned
    assert "Freedom Blues" in owned  # Burnice's primary 4pc
    # meta scope covers far more sets than her single-roster plan
    meta_page = client.get("/ui/farm?scope=meta").text
    assert meta_page.count("<tr>") > owned.count("<tr>")


def test_ui_farm_page_nav_link(client, ui_player):
    page = client.get("/ui")
    assert '/ui/farm' in page.text
