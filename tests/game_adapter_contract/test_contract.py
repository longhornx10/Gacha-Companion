"""Adapter contract suite: identical core scenarios against ZZZ and example game.

Proves the core never assumes: 3-member teams, Drive Discs, W-Engines,
Mindscapes, ZZZ stat names, ZZZ resources or ZZZ endgame modes.
"""

import pytest

from game_companion.core.games.base import GameAdapter
from game_companion.core.games.registry import get_adapter

ADAPTER_IDS = ["zzz", "example"]


@pytest.mark.parametrize("game_id", ADAPTER_IDS)
def test_adapter_exposes_full_contract(game_id):
    adapter = get_adapter(game_id)
    assert isinstance(adapter, GameAdapter)
    assert adapter.game_id == game_id
    assert adapter.display_name
    term = adapter.terminology()
    for noun in (term.character, term.equipment, term.gear, term.duplication, term.special_progression):
        assert noun, "terminology nouns must be non-empty"
    assert adapter.team_rules().min_size <= adapter.team_rules().max_size
    assert adapter.gear_slots(), "gear slots must be defined"
    assert adapter.stat_definitions()
    assert adapter.skill_definitions()
    assert adapter.resource_definitions()
    assert adapter.screenshot_specs(), "at least one screenshot schema expected"


@pytest.mark.parametrize("game_id", ADAPTER_IDS)
def test_team_sizes_differ_per_game_and_core_enforces_both(client, player, game_id):
    adapter = get_adapter(game_id)
    size = adapter.team_rules().max_size
    keys = [f"char_{game_id}_{i}" for i in range(size + 1)]
    for key in keys:
        response = client.post(f"/api/games/{game_id}/characters", json={"key": key})
        assert response.status_code == 201

    # max-size team accepted
    ok = client.post(f"/api/games/{game_id}/teams", json={
        "name": "Full", "members": [{"character": k} for k in keys[:size]],
    })
    assert ok.status_code == 201

    # size+1 team rejected, error text uses THIS game's terminology
    too_many = client.post(f"/api/games/{game_id}/teams", json={
        "name": "Too Many", "members": [{"character": k} for k in keys],
    })
    assert too_many.status_code == 422
    assert adapter.terminology().character in too_many.json()["detail"]["message"]


@pytest.mark.parametrize("game_id", ADAPTER_IDS)
def test_gear_slots_and_thresholds_are_adapter_defined(client, player, game_id):
    adapter = get_adapter(game_id)
    slot_key = adapter.gear_slots()[0].key
    created = client.post(f"/api/games/{game_id}/gear", json={
        "slot": slot_key, "main_stat_key": adapter.stat_definitions()[0].key,
    })
    assert created.status_code == 201

    # a ZZZ slot key ('1') must be invalid in the example game and vice versa
    other = get_adapter("example" if game_id == "zzz" else "zzz")
    other_slot = other.gear_slots()[0].key
    wrong = client.post(f"/api/games/{game_id}/gear", json={"slot": other_slot})
    assert wrong.status_code == 422

    # thresholds: definition list + evaluation endpoint work for both games
    resource = adapter.resource_definitions()[0]
    status = client.put(
        f"/api/games/{game_id}/resources/{resource.key}", json={"quantity": 10}
    ).json()
    assert status["status"] in ("done", "prep", "very_low", "critically_low", "unknown")


@pytest.mark.parametrize("game_id", ADAPTER_IDS)
def test_exports_use_game_terminology(client, player, game_id):
    adapter = get_adapter(game_id)
    character_key = f"term_{game_id}"
    assert client.post(
        f"/api/games/{game_id}/characters", json={"key": character_key}
    ).status_code == 201
    written = client.post(f"/api/games/{game_id}/exports").json()["written"]
    roster_md = open([p for p in written if p.endswith("roster.md")][0]).read()
    assert adapter.terminology().character in roster_md
    gear_md = open([p for p in written if p.endswith("gear.md")][0]).read()
    assert adapter.terminology().gear in gear_md


@pytest.mark.parametrize("game_id", ADAPTER_IDS)
def test_scoring_hooks_return_labeled_components(game_id):
    adapter = get_adapter(game_id)
    roster_size = 4 if game_id == "example" else 3
    members = [f"m{i}" for i in range(roster_size)]
    components = adapter.score_team(members, {})
    assert components, "score_team must return explainable components"
    for component in components:
        assert component.label in ("HEURISTIC", "MEASURED", "CONSENSUS")
        assert 0 <= component.value <= component.max_value
