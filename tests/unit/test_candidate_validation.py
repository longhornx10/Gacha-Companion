"""Screenshot candidate validation (M5): schema gates, honesty rules."""

import pytest

from game_companion.core.games.registry import get_adapter
from game_companion.core.vision.service import diff_candidate, validate_candidate
from game_companion.errors import ValidationError


@pytest.fixture()
def zzz():
    return get_adapter("zzz")


def test_agent_overview_candidate_valid(zzz):
    candidate = validate_candidate(zzz, "character_overview", {
        "character_name": "Burnice White", "level": 60, "duplication_level": 1,
    })
    assert candidate["level"] == 60
    assert candidate["duplication_level"] == 1


def test_out_of_range_values_rejected(zzz):
    with pytest.raises(ValidationError):
        validate_candidate(zzz, "character_overview", {"level": 999})
    with pytest.raises(ValidationError):
        validate_candidate(zzz, "character_overview", {"duplication_level": 12})


def test_unknown_screen_type_rejected(zzz):
    with pytest.raises(ValidationError):
        validate_candidate(zzz, "nonexistent_screen", {})


def test_disc_detail_max_four_substats(zzz):
    substats = [{"key": f"s{i}", "value": 1.0} for i in range(5)]
    with pytest.raises(ValidationError):
        validate_candidate(zzz, "gear_detail", {"substats": substats})


def test_disc_detail_candidate_normalizes(zzz):
    candidate = validate_candidate(zzz, "gear_detail", {
        "slot": "5", "main_stat_key": "crit_rate", "main_stat_value": 24.0,
        "substats": [{"key": "crit_dmg", "value": 46.0, "rolls": 5}],
    })
    assert candidate["substats"][0]["rolls"] == 5


def test_diff_proposes_not_mutates(zzz, client, player):
    from tests.conftest import make_character

    make_character(client, "zzz", "burnice", level=1)
    session = client.app.state.session_factory()
    try:
        diff = diff_candidate(
            session, zzz, "zzz", player, "character_overview",
            {"character_name": "Burnice White", "level": 60, "mindscape": 2}, "burnice",
        )
    finally:
        session.close()
    updates = [c for c in diff["changes"] if c["action"] == "update"]
    assert any(c["field"] == "level" and c["current"] == 1 and c["proposed"] == 60 for c in updates)


def test_schemas_and_prompts_differ_per_game():
    """Generic keys, game-specific content: extraction schemas and prompts must
    differ between games even though both use the 'character_overview' key."""
    zzz = get_adapter("zzz")
    example = get_adapter("example")
    zzz_spec = zzz.screenshot_specs()["character_overview"]
    example_spec = example.screenshot_specs()["character_overview"]
    assert zzz_spec.schema is not example_spec.schema
    assert zzz_spec.prompt != example_spec.prompt
