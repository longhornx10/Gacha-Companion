"""Resources (M12), codes (M8), combat history trends (M17), training (M18)."""


def test_resource_statuses_via_api(client, player):
    # ZZZ ships no fabricated requirement numbers -> unknown status, honestly.
    r1 = client.put("/api/games/zzz/resources/agent_exp", json={"quantity": 1000}).json()
    assert r1["status"] == "unknown"
    assert "refusing to guess" in r1["explanation"]

    # example game ships known single-max values -> deterministic statuses
    r2 = client.put("/api/games/example/resources/crystal", json={"quantity": 700}).json()
    assert r2["status"] == "done"  # 700 >= single_max 500 (no plan entries)

    # plan entries create demand Y
    client.post("/api/games/example/characters", json={"key": "aria"})
    client.post("/api/games/example/characters", json={"key": "brann"})
    aria = client.get("/api/games/example/characters/aria").json()
    brann = client.get("/api/games/example/characters/brann").json()
    planned = client.put("/api/games/example/resources/plan/crystal", json={
        "entries": [{"character": aria["id"], "amount": 500}, {"character": brann["id"], "amount": 500}],
    }).json()
    assert planned["plan"][0]["amount"] == 500
    assert planned["status"]["status"] == "prep"  # 700 >= X=500, < Y=1000

    listing = client.get("/api/games/example/resources").json()["resources"]
    crystal = [r for r in listing if r["resource_key"] == "crystal"][0]
    assert crystal["planned_total"] == 1000


def test_codes_lifecycle_and_markdown(client, player):
    code = client.post("/api/games/zzz/codes", json={"code": "ZZZFREE100"}).json()
    assert code["used"] is False

    client.post("/api/games/zzz/codes", json={"code": "OLDCODE", "status": "expired"})
    client.post("/api/games/zzz/codes", json={"code": "RECYCLED", "status": "recycled"})

    duplicate = client.post("/api/games/zzz/codes", json={"code": "ZZZFREE100"})
    assert duplicate.status_code == 422

    client.post(f"/api/games/zzz/codes/{code['id']}/mark-used")

    markdown = client.get("/api/games/zzz/codes.md").text
    assert "~~`ZZZFREE100`~~" in markdown          # used -> strikethrough
    assert "`RECYCLED` ♻ reactivated" in markdown  # recycled stays visible
    assert "`OLDCODE` (expired)" in markdown


def test_combat_history_trends(client, player):
    from tests.conftest import make_character

    for key in ("burnice", "ellen", "lycaon"):
        make_character(client, "zzz", key)
    team = client.post("/api/games/zzz/teams", json={
        "name": "Raid Team",
        "members": [{"character": "burnice"}, {"character": "ellen"}, {"character": "lycaon"}],
        "is_active": True,
    }).json()

    scores = [100, 200, 300, 800]
    for score in scores:
        result = client.post("/api/games/zzz/combat-results", json={
            "encounter_key": "deadly_assault", "encounter_slot": "1",
            "cleared": True, "stars": 3, "score": score, "team_id": team["id"],
        })
        assert result.status_code == 201, result.text

    trends = client.get("/api/games/zzz/combat-results/trends").json()
    assert trends["total_attempts"] == 4
    assert trends["win_rate"] == 1.0
    assert trends["by_team"]["Raid Team"]["attempts"] == 4
    assert trends["improvement"]["recent_average_score"] > trends["improvement"]["early_average_score"]

    # snapshots, not live references
    results = client.get("/api/games/zzz/combat-results").json()["results"]
    assert results[0]["team_snapshot"]["members"][0]["key"] == "burnice"


def test_training_issue_recurrence(client, player):
    first = client.post("/api/games/zzz/training/issues", json={
        "category": "swap_timing", "description": "drops the buff during swaps",
        "character_keys": ["burnice"],
    }).json()
    assert first["recurred"] is False

    second = client.post("/api/games/zzz/training/issues", json={
        "category": "swap_timing", "description": "drops the buff during swaps",
        "character_keys": ["burnice"],
    }).json()
    assert second["recurred"] is True
    assert second["occurrences"] == 2

    focus = client.get("/api/games/zzz/training/focus").json()
    assert focus["focus"][0]["occurrences"] == 2

    resolved = client.patch(f"/api/games/zzz/training/issues/{second['issue_id']}",
                            json={"status": "resolved"})
    assert resolved.json()["status"] == "resolved"
