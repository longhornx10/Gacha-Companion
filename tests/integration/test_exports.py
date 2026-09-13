"""Exports (JSON + Markdown) and terminology flow-through."""

import json


def test_json_and_markdown_exports(client, player, tmp_path):
    from tests.conftest import make_character

    make_character(client, "zzz", "burnice", level=60, duplication_level=1)
    client.put("/api/games/zzz/characters/burnice/skills",
               json={"skills": {"basic_attack": 12, "core_skill": 5}})
    client.post("/api/games/zzz/gear", json={
        "slot": "5", "set_key": "fanged_metal", "main_stat_key": "crit_rate", "level": 15,
    })
    client.post("/api/games/zzz/codes", json={"code": "ZZZFREE100"})
    client.put("/api/games/zzz/resources/dennies", json={"quantity": 123456})

    written = client.post("/api/games/zzz/exports").json()["written"]
    assert any(p.endswith("account.json") for p in written)
    assert any(p.endswith("roster.md") for p in written)
    assert any(p.endswith("codes.md") for p in written)

    roster_md = open([p for p in written if p.endswith("roster.md")][0]).read()
    assert "## Burnice (`burnice`)" in roster_md
    assert "Mindscape 1" in roster_md            # ZZZ terminology, not "duplication"
    assert "Basic Attack 12" in roster_md

    codes_md = open([p for p in written if p.endswith("codes.md")][0]).read()
    assert "`ZZZFREE100`" in codes_md

    account = json.loads(open([p for p in written if p.endswith("account.json")][0]).read())
    assert account["game"]["game_id"] == "zzz"
    assert account["characters"][0]["skills"]["basic_attack"] == 12
    assert account["resources"][0]["quantity"] == 123456


def test_export_json_endpoint(client, player):
    from tests.conftest import make_character

    make_character(client, "example", "aria", level=20)
    response = client.get("/api/games/example/export.json")
    assert response.status_code == 200
    data = response.json()
    assert data["characters"][0]["key"] == "aria"
    assert data["game"]["display_name"].startswith("Aether")


def test_export_regenerable_and_gear_uses_game_term(client, player):
    from tests.conftest import make_character

    make_character(client, "example", "aria")
    client.post("/api/games/example/gear", json={
        "slot": "talisman", "main_stat_key": "power", "level": 3,
    })
    written = client.post("/api/games/example/exports").json()["written"]
    gear_md = open([p for p in written if p.endswith("gear.md")][0]).read()
    assert "Charm Inventory" in gear_md  # example-game terminology
    assert "slot talisman" in gear_md
