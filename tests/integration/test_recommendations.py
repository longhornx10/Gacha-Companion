"""Recommendations (M9-M16), tutor (M7) and their honesty guarantees."""

from tests.conftest import MockLLM, make_zzz_roster


def _zzz_team_of_5(client, player: str):
    return make_zzz_roster(client, player, ["burnice", "ellen", "lycaon", "lucy", "anby"])


def test_team_recommendations_use_roster_and_components(client, player):
    _zzz_team_of_5(client, player)
    result = client.post("/api/games/zzz/recommendations/teams").json()
    assert result["best_owned"]
    top = result["best_owned"][0]
    assert len(top["members"]) == 3
    assert top["total_label"] == "HEURISTIC"
    names = {c["name"] for c in top["components"]}
    assert {"role_balance", "build_readiness", "encounter_fit"} <= names
    assert result["note"].lower().startswith("heuristic")


def test_team_recommendations_flag_active_team_overlap(client, player):
    _zzz_team_of_5(client, player)
    client.post("/api/games/zzz/teams", json={
        "name": "Committed",
        "members": [{"character": "burnice"}, {"character": "ellen"}, {"character": "lycaon"}],
        "is_active": True,
    })
    result = client.post("/api/games/zzz/recommendations/teams").json()
    top = result["best_owned"][0]
    if set(top["members"]) & {"burnice", "ellen", "lycaon"}:
        assert top["overlaps_active_teams"]


def test_gear_inventory_evaluation(client, player):
    make_zzz_roster(client, player, ["burnice", "ellen"])
    strong = client.post("/api/games/zzz/gear", json={
        "slot": "5", "main_stat_key": "crit_rate",
        "substats": [{"key": "crit_dmg", "value": 0.48}, {"key": "atk_pct", "value": 0.3}],
    }).json()
    trash = client.post("/api/games/zzz/gear", json={
        "slot": "3", "main_stat_key": "def", "substats": [],
    }).json()
    result = client.post("/api/games/zzz/recommendations/gear-inventory").json()
    discard_ids = {g["gear_id"] for g in result["likely_safe_to_discard"]}
    assert trash["id"] in discard_ids
    assert strong["id"] not in discard_ids
    for entries in result["best_for"].values():
        for entry in entries:
            assert "score" in entry


def test_audit_flags_incomplete_and_stale(client, player):
    client.post("/api/games/zzz/characters", json={"key": "burnice", "level": 10})
    result = client.post("/api/games/zzz/recommendations/audit").json()
    entry = result["results"][0]
    codes = {issue["code"] for issue in entry["issues"]}
    assert entry["status"] in ("attention", "critical")
    assert "never_verified" in codes
    assert "missing_skill" in codes or "build_incomplete" in codes


def test_upgrade_plan_is_prioritized_and_honest(client, player):
    make_zzz_roster(client, player, ["burnice", "ellen", "lucy"])
    client.post("/api/games/zzz/teams", json={
        "name": "Main",
        "members": [{"character": "burnice"}, {"character": "ellen"}, {"character": "lucy"}],
        "is_active": True,
    })
    client.put("/api/games/zzz/characters/burnice/skills", json={"skills": {"basic_attack": 5}})
    plan = client.post("/api/games/zzz/recommendations/plan").json()
    assert plan["actions"]
    burnice_actions = [a for a in plan["actions"] if a["character"] == "burnice"]
    assert burnice_actions, "active team members with gaps must get actions"
    assert "not known" in plan["honesty_note"] or "claimed" in plan["honesty_note"]


def test_equipment_compare_ranking(client, player):
    make_zzz_roster(client, player, ["burnice"])
    client.post("/api/games/zzz/equipment", json={
        "key": "spring", "display_name": "Spring Empyrean", "rarity": "S", "level": 60, "refinement": 5,
        "character": "burnice",
    })
    client.post("/api/games/zzz/equipment", json={
        "key": "weaker", "display_name": "Weaker Engine", "rarity": "A", "level": 1,
    })
    result = client.post("/api/games/zzz/recommendations/equipment-compare", json={
        "character": "burnice",
    }).json()
    ranking = result["ranking"]
    assert len(ranking) == 2
    assert ranking[0]["quality"]["label"] == "HEURISTIC"
    assert result["currently_equipped"] == ranking[0]["item_id"] or any(
        r["equipped_by"] == "burnice" for r in ranking
    )
    assert "no DPS percentages" in result["note"]


def test_optimize_endpoint_with_adapter_encounter_mode(client, player):
    make_zzz_roster(client, player, [
        "burnice", "ellen", "lycaon", "lucy", "anby",
        "soukaku", "koleda", "grace", "qingyi", "rina",
    ])
    response = client.post("/api/games/zzz/recommendations/optimize", json={
        "encounter_key": "deadly_assault", "objective": "maximize_total",
    })
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["feasible"] is True
    assert len(data["best"]["teams"]) == 3
    assigned = [m for team in data["best"]["teams"] for m in team["members"]]
    assert len(assigned) == 9
    assert len(set(assigned)) == 9, "no character may appear on two teams"
    assert "HEURISTIC" in data["score_warning"]
    assert data["explanation"] is not None


def test_tutor_uses_context_and_persona(client, player, monkeypatch):
    make_zzz_roster(client, player, ["burnice"])
    mock = MockLLM(complete_text="Here is how Burnice works (mock).")
    monkeypatch.setattr(client.app.state, "llm", mock, raising=False)
    response = client.post("/api/games/zzz/tutor/explain", json={
        "character": "burnice", "topic": "kit", "mode": "simple", "persona_id": "calm_tactician",
    })
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["explanation"].startswith("Here is how Burnice")
    assert data["context_used"]["character"]["key"] == "burnice"
    system_message = mock.calls[0]["messages"][0]["content"]
    assert "calm" in system_message or "Calm" in system_message
    assert "TONE ONLY" in system_message


def test_tutor_without_llm_returns_503(client, player):
    make_zzz_roster(client, player, ["burnice"])
    response = client.post("/api/games/zzz/tutor/explain", json={"character": "burnice"})
    assert response.status_code == 503
