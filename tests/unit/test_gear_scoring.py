"""ZZZ gear scoring: heuristic verdicts with reasons (M11)."""

from game_companion.core.games.registry import get_adapter


def test_crit_piece_for_attack_archetype_scores_strong():
    zzz = get_adapter("zzz")
    evaluation = zzz.score_gear(
        {"slot": "5", "main_stat_key": "crit_rate", "substats": [
            {"key": "crit_dmg", "value": 0.48}, {"key": "atk_pct", "value": 0.30},
        ]},
        {"character_key": "ellen", "owned_specialties": ["attack"]},
    )
    assert evaluation.label == "HEURISTIC"
    assert evaluation.verdict in ("strong", "useful")
    assert evaluation.reasons, "scoring must explain itself"
    assert any("crit_rate" in reason for reason in evaluation.reasons)


def test_unknown_character_uses_best_fit_archetype_with_note():
    zzz = get_adapter("zzz")
    evaluation = zzz.score_gear({"main_stat_key": None, "substats": []}, {})
    assert any("best-fit archetype" in reason for reason in evaluation.reasons)


def test_good_rolls_for_unowned_archetype_are_speculative():
    zzz = get_adapter("zzz")
    evaluation = zzz.score_gear(
        {"slot": "4", "main_stat_key": "anomaly_proficiency", "substats": [
            {"key": "anomaly_proficiency", "value": 9.0},
        ]},
        {"owned_specialties": ["attack"]},
    )
    assert evaluation.verdict == "speculative"


def test_empty_gear_is_weak_or_discardable():
    zzz = get_adapter("zzz")
    evaluation = zzz.score_gear({"substats": []}, {"owned_specialties": ["attack"]})
    assert evaluation.verdict in ("weak", "likely_safe_to_discard")


def test_example_game_scoring_is_independent():
    example = get_adapter("example")
    evaluation = example.score_gear({"main_stat_key": "power", "substats": []}, {"role": "striker"})
    assert evaluation.verdict in ("strong", "useful")
