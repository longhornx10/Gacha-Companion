"""Core CRUD flows over the API: characters, skills, equipment, gear, builds,
teams (incl. mutual exclusion and gear claiming), and player/game isolation."""



# -- characters & skills -------------------------------------------------------


def test_character_crud_and_skill_validation(client, player):
    char = client.post("/api/games/zzz/characters", json={
        "key": "burnice", "level": 60, "data": {"specialty": "anomaly"},
    }).json()
    assert char["duplication_level"] is None  # partial records supported

    updated = client.patch("/api/games/zzz/characters/burnice", json={
        "level": 60, "duplication_level": 1, "verified": True,
    }).json()
    assert updated["duplication_level"] == 1
    assert updated["last_verified_at"] is not None

    skills = client.put("/api/games/zzz/characters/burnice/skills", json={
        "skills": {"basic_attack": 12, "core_skill": 5},
    }).json()
    assert skills["skills"] == {"basic_attack": 12, "core_skill": 5}

    # unknown skill key rejected with the known set
    response = client.put("/api/games/zzz/characters/burnice/skills", json={
        "skills": {"trance": 10},
    })
    assert response.status_code == 422
    assert "known:" in response.json()["detail"]["message"]

    # out-of-range level rejected
    response = client.put("/api/games/zzz/characters/burnice/skills", json={
        "skills": {"basic_attack": 99},
    })
    assert response.status_code == 422

    # resolve by key works
    fetched = client.get("/api/games/zzz/characters/burnice").json()
    assert fetched["skills"]["basic_attack"] == 12
    assert "builds" in fetched


def test_character_data_validation_is_game_specific(client, player):
    ok = client.post("/api/games/zzz/characters", json={"key": "ellen", "data": {"attribute": "ice"}})
    assert ok.status_code == 201
    bad = client.post("/api/games/zzz/characters", json={"key": "weird", "data": {"attribute": "toaster"}})
    assert bad.status_code == 422

    # same key is invalid in the example game but fine if data is empty
    ok_example = client.post("/api/games/example/characters", json={"key": "aria", "data": {"tag": "wind"}})
    assert ok_example.status_code == 201
    bad_example = client.post("/api/games/example/characters", json={"key": "dusk", "data": {"tag": "toaster"}})
    assert bad_example.status_code == 422


# -- equipment & gear ------------------------------------------------------------


def test_equipment_equip_is_exclusive_per_character(client, player):
    client.post("/api/games/zzz/characters", json={"key": "burnice"})
    item_a = client.post("/api/games/zzz/equipment", json={
        "key": "wengine_a", "display_name": "W-Engine A", "rarity": "S", "level": 60,
    }).json()
    item_b = client.post("/api/games/zzz/equipment", json={
        "key": "wengine_b", "display_name": "W-Engine B", "rarity": "A", "level": 10,
        "character": "burnice",
    }).json()
    assert item_b["equipped_character_id"]

    # equipping A to burnice unequips B
    client.patch(f"/api/games/zzz/equipment/{item_a['id']}", json={"character": "burnice"})
    refreshed_b = client.get(f"/api/games/zzz/equipment/{item_b['id']}").json()
    assert refreshed_b["equipped_character_id"] is None


def test_gear_slot_validation_and_build_claiming(client, player):
    client.post("/api/games/zzz/characters", json={"key": "burnice"})
    client.post("/api/games/zzz/characters", json={"key": "ellen"})
    build = client.post("/api/games/zzz/characters/burnice/builds", json={"name": "fire"}).json()
    disc = client.post("/api/games/zzz/gear", json={
        "slot": "5", "set_key": "fanged_metal", "main_stat_key": "crit_rate",
        "substats": [{"key": "crit_dmg", "value": 0.4}],
    }).json()

    bad_slot = client.put(f"/api/games/zzz/characters/burnice/builds/{build['id']}/slots",
                          json={"slot": "9", "gear_item_id": disc["id"]})
    assert bad_slot.status_code == 422

    result = client.put(f"/api/games/zzz/characters/burnice/builds/{build['id']}/slots",
                        json={"slot": "5", "gear_item_id": disc["id"]}).json()
    assert result["gear_item_id"] == disc["id"]

    activated = client.post(f"/api/games/zzz/characters/burnice/builds/{build['id']}/activate").json()
    assert activated["active"] is True

    gear_row = client.get(f"/api/games/zzz/gear/{disc['id']}").json()
    assert gear_row["equipped_character_id"]

    # Steal the disc with another character's active build -> deterministic move.
    ellen_build = client.post("/api/games/zzz/characters/ellen/builds", json={"name": "ice"}).json()
    put_result = client.put(f"/api/games/zzz/characters/ellen/builds/{ellen_build['id']}/slots",
                            json={"slot": "5", "gear_item_id": disc["id"]}).json()
    ellen_activation = client.post(
        f"/api/games/zzz/characters/ellen/builds/{ellen_build['id']}/activate"
    ).json()
    all_moves = put_result["moves"] + ellen_activation["moves"]
    assert any("moved out" in m for m in all_moves)

    gear_row = client.get(f"/api/games/zzz/gear/{disc['id']}").json()
    assert gear_row["equipped_character_id"]

    # Burnice's build stays active, but the stolen slot was cleared deterministically.
    burnice_builds = client.get("/api/games/zzz/characters/burnice/builds").json()["builds"]
    burnice_fire = [b for b in burnice_builds if b["name"] == "fire"][0]
    assert burnice_fire["gear_slots"]["5"] is None
    assert burnice_fire["is_active"] is True


# -- teams --------------------------------------------------------------------------


def test_team_size_is_adapter_specific(client, player):
    from tests.conftest import make_character

    for key in ("burnice", "ellen", "lycaon"):
        make_character(client, "zzz", key)
    for key in ("aria", "brann", "cinder", "dusk"):
        make_character(client, "example", key)

    too_small_example = client.post("/api/games/example/teams", json={
        "name": "G1", "members": [{"character": "aria"}, {"character": "brann"}, {"character": "cinder"}],
    })
    assert too_small_example.status_code == 422
    assert "4" in too_small_example.json()["detail"]["message"]

    ok_example = client.post("/api/games/example/teams", json={
        "name": "G1",
        "members": [{"character": "aria"}, {"character": "brann"},
                    {"character": "cinder"}, {"character": "dusk"}],
    })
    assert ok_example.status_code == 201

    too_big_zzz = client.post("/api/games/zzz/teams", json={
        "name": "T1",
        "members": [{"character": "burnice"}, {"character": "ellen"}, {"character": "lycaon"}],
    })
    assert too_big_zzz.status_code == 201  # exactly 3 is fine for zzz

    duplicate_member = client.post("/api/games/zzz/teams", json={
        "name": "T2",
        "members": [{"character": "burnice"}, {"character": "burnice"}, {"character": "ellen"}],
    })
    assert duplicate_member.status_code == 422


def test_active_team_exclusion(client, player):
    from tests.conftest import make_character

    for key in ("burnice", "ellen", "lycaon", "anby"):
        make_character(client, "zzz", key)
    team_a = client.post("/api/games/zzz/teams", json={
        "name": "A", "members": [{"character": "burnice"}, {"character": "ellen"}, {"character": "lycaon"}],
        "is_active": True,
    }).json()
    assert team_a["is_active"]

    conflict = client.post("/api/games/zzz/teams", json={
        "name": "B", "members": [{"character": "burnice"}, {"character": "anby"}, {"character": "ellen"}],
        "is_active": True,
    })
    assert conflict.status_code == 409
    assert "burnice" in conflict.json()["detail"]["message"].lower()


# -- isolation ------------------------------------------------------------------------


def test_player_and_game_isolation(client, player, second_player):
    from tests.conftest import make_character

    # with two players present, scoping must be explicit
    make_character(client, "zzz", "burnice", player_id=player)
    make_character(client, "example", "aria", player_id=player)

    # the other player sees nothing of player 1's data
    zzz_second = client.get(f"/api/games/zzz/characters?player_id={second_player}").json()
    assert zzz_second["characters"] == []

    # game isolation: zzz roster does not leak into example listing
    zzz_list = client.get(f"/api/games/zzz/characters?player_id={player}").json()["characters"]
    example_list = client.get(f"/api/games/example/characters?player_id={player}").json()["characters"]
    assert {c["key"] for c in zzz_list} == {"burnice"}
    assert {c["key"] for c in example_list} == {"aria"}

    # cross-player reads of a specific character are a 404, not a leak
    assert client.get(f"/api/games/zzz/characters/burnice?player_id={second_player}").status_code == 404

    # unknown game rejected
    assert client.get(f"/api/games/hsr/characters?player_id={player}").status_code == 404
