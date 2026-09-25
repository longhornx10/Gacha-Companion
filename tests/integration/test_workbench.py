"""M24: terminology tables, gear families, bootstrap pipeline, new-game scaffold."""

from __future__ import annotations

import httpx
import pytest

from game_companion.core.games.registry import get_adapter
from game_companion.core.games.terminology import REQUIRED_KEYS, terminology_block

ADAPTER_IDS = ["zzz", "example", "hsr", "nte"]


@pytest.mark.parametrize("game_id", ADAPTER_IDS)
def test_terminology_table_has_required_ontology(game_id):
    table = get_adapter(game_id).terminology_table()
    assert table, "every shipped adapter must carry a terminology table"
    keys = {row["key"] for row in table}
    for required in REQUIRED_KEYS:
        assert required in keys, f"{game_id} missing terminology key '{required}'"
        row = next(r for r in table if r["key"] == required)
        assert row.get("display"), f"{game_id}:{required} needs a display name"


def test_terminology_block_is_game_specific():
    zzz = terminology_block("Zenless Zone Zero", get_adapter("zzz").terminology_table())
    hsr = terminology_block("Honkai: Star Rail", get_adapter("hsr").terminology_table())
    assert "Agent" in zzz and "Agent" not in hsr
    assert "Light Cone" in hsr and "Light Cone" not in zzz
    assert "Polychrome" in zzz and "Stellar Jade" in hsr


def test_currency_categories_unify_across_games():
    """The Polychrome/Stellar Jade/Annulith promise: one category, three names."""
    categories = {}
    for game_id in ADAPTER_IDS:
        rows = {
            d.key: d.category
            for d in get_adapter(game_id).resource_definitions()
            if d.category
        }
        categories[game_id] = rows
    assert categories["zzz"]["polychrome"] == "pull_currency"
    assert categories["hsr"]["stellar_jade"] == "pull_currency"
    assert categories["nte"]["annulith"] == "pull_currency"


def test_gear_families_cover_slots_and_are_validated(client, player):
    hsr = get_adapter("hsr")
    families = hsr.gear_families()
    assert {f.key for f in families} == {"relic", "ornament"}
    slot_keys = {s.key for s in hsr.gear_slots()}
    assert slot_keys == {"head", "hands", "body", "feet", "sphere", "rope"}

    # gear_type defaults to the first family and validates against declared ones
    relic = client.post("/api/games/hsr/gear", json={"slot": "head"}).json()
    assert relic["gear_type"] == "relic"
    ornament = client.post(
        "/api/games/hsr/gear", json={"gear_type": "ornament", "slot": "sphere"}
    ).json()
    assert ornament["gear_type"] == "ornament"
    bad = client.post("/api/games/hsr/gear", json={"gear_type": "disc", "slot": "head"})
    assert bad.status_code == 422


def test_nte_module_combo_set_rule_is_adapter_data():
    nte = get_adapter("nte")
    cartridge = nte.gear_families()[0]
    assert cartridge.set_rule == "module_combo"
    assert nte.gear_families() != get_adapter("hsr").gear_families()


def test_bootstrap_stages_changes_with_provenance(client, settings, player):
    payload = {
        "1001": {"id": "1001", "name": "March 7th", "path": "warrior", "element": "ice", "rarity": 4},
        "1002": {"id": "1002", "name": "Dan Heng", "path": "rogue", "element": "wind", "rarity": 4},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    transport = httpx.MockTransport(handler)
    from game_companion.core.bootstrap.pipeline import BootstrapService

    service = BootstrapService(_session(client), get_adapter("hsr"), settings)
    summary = service.run("starrailres", transport=transport, apply=True)
    service.session.commit()  # make staged rows visible to the API session

    assert summary["staged"] == 2
    assert summary["applied"] is True
    assert summary["provenance"]["url"].startswith("https://raw.githubusercontent.com/Mar-7th")

    changes = client.get("/api/games/hsr/changes?review_status=pending").json()["changes"]
    assert len(changes) == 2
    row = next(c for c in changes if c["entity_key"] == "1001")
    assert row["proposed_value"]["name"] == "March 7th"
    assert row["evidence"][0]["source"] == "starrailres"
    assert "retrieved_at" in row["evidence"][0]

    # provenance-tagged data file lands in the DATA DIR, not the repo
    applied = __import__("pathlib").Path(summary["applied_path"])
    assert applied.exists()
    document = __import__("json").loads(applied.read_text())
    assert document["_meta"]["review"] == "machine_staged"
    assert document["_meta"]["source"].startswith("https://")
    assert len(document["rows"]) == 2


def test_bootstrap_unknown_source_and_empty_transform(client, settings):
    from game_companion.core.bootstrap.pipeline import BootstrapService
    from game_companion.errors import NotFoundError

    service = BootstrapService(_session(client), get_adapter("hsr"), settings)
    with pytest.raises(NotFoundError):
        service.run("does-not-exist", transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={})
        ))

    # nte declares no bootstrap sources yet (no stable NTE API exists)
    from game_companion.errors import ValidationError

    service_nte = BootstrapService(_session(client), get_adapter("nte"), settings)
    with pytest.raises(ValidationError):
        service_nte.run("auto", transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={})
        ))


def test_zzz_bootstrap_transform_is_shape_tolerant(client, settings):
    """hakush.in ZZZ: dict keyed by id; numeric element codes mapped; junk skipped."""
    from game_companion.core.bootstrap.pipeline import BootstrapService

    payload = {
        "1401": {"id": "1401", "name": "Hoshimi Miyabi", "rank": "S", "element": 203, "type": 4},
        "1191": {"id": "1191", "name": "Soldier 11", "rank": "S", "element": "Fire", "specialty": "attack"},
        "junk": {"no_name_here": True},
        "not-a-dict": 7,
    }
    service = BootstrapService(_session(client), get_adapter("zzz"), settings)
    summary = service.run(
        "hakush", transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    )
    service.session.commit()
    assert summary["staged"] == 2, "nameless/unparseable rows must be skipped, not guessed"
    changes = client.get("/api/games/zzz/changes?review_status=pending").json()["changes"]
    miyabi = next(c for c in changes if c["entity_key"] == "1401")
    assert miyabi["proposed_value"]["attribute"] == "electric"  # numeric code 203 mapped
    assert miyabi["is_new"] if "is_new" in miyabi else True


def test_new_game_scaffold_creates_working_package(tmp_path, monkeypatch):

    from game_companion.core.games import scaffold

    # scaffold into a throwaway games dir (copy of the real one is unnecessary)
    fake_root = tmp_path / "games"
    fake_root.mkdir()
    target = scaffold.scaffold_new_game("demo_game", fake_root)
    registry = scaffold.register_installed("demo_game", fake_root)

    assert (target / "adapter.py").exists()
    assert (target / "data" / "terminology.json").exists()
    assert (target / "prompts" / "character_overview.md").exists()
    import json

    assert json.loads(registry.read_text())["adapters"]["demo_game"].endswith("Adapter")

    # the generated adapter.py is valid Python
    compile((target / "adapter.py").read_text(), "adapter.py", "exec")

    # id validation: no dupes, no weird ids
    from game_companion.errors import ValidationError

    with pytest.raises(ValidationError):
        scaffold.scaffold_new_game("demo_game", fake_root)
    with pytest.raises(ValidationError):
        scaffold.scaffold_new_game("Bad-Id", fake_root)


def _session(client):
    from game_companion.config import get_settings
    from game_companion.db.session import create_db_engine, create_session_factory

    engine = create_db_engine(get_settings().resolved_database_url)
    return create_session_factory(engine)()
