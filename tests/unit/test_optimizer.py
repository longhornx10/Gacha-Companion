"""Multi-team optimizer (M15): the SPEC reallocation scenario + guarantees."""

from game_companion.core.teams.optimizer import optimize_team_allocation


def _make_score_fn(slot_preferences):
    """slot_preferences: list of dicts {member: score}. Team score = sum of members."""

    def score(members, slot_index):
        prefs = slot_preferences[slot_index]
        total = sum(prefs.get(m, 3.0) for m in members)
        return total, [{"name": "fit", "value": total, "max": 30, "label": "HEURISTIC", "detail": ""}]

    return score


def test_spec_reallocation_scenario():
    """SPEC: Team1 with X = 100, without X = 60; reallocating X gives a better
    global outcome (85 + 100). The optimizer must find the global best, not
    the greedy per-slot pick."""
    slots = [
        {"x": 10.0, "a": 5.0, "b": 6.0},  # slot 0 loves x
        {"y": 10.0, "x": 10.0, "c": 4.0},  # slot 1 loves x equally -> conflict
    ]
    roster = ["x", "a", "b", "c", "y"]
    result = optimize_team_allocation(roster, 2, 2, _make_score_fn(slots))
    assert result.feasible
    assert result.best is not None
    # Greedy: slot0 grabs (b,x)=16, leaving slot1 (c,y)=14 -> total 30.
    # Global optimum: slot1 takes (x,y)=20, slot0 takes (a,b)=11 -> total 31.
    assert result.best.total >= result.greedy.total
    assert result.best.total > result.greedy.total, "spec scenario must favor reallocation"
    assert result.explanation, "a decisive reallocation must be explained"
    assert any("global optimization gains" in line for line in result.explanation)


def test_characters_never_repeat_across_teams():
    slots = [{m: 10.0 for m in ["a", "b", "c", "d", "e", "f"]} for _ in range(3)]
    result = optimize_team_allocation(["a", "b", "c", "d", "e", "f"], 3, 2, _make_score_fn(slots))
    assigned = [m for team in result.best.teams for m in team["members"]]
    assert len(assigned) == len(set(assigned)) == 6
    assert result.best.total == 60.0


def test_infeasible_when_roster_too_small():
    result = optimize_team_allocation(["a", "b"], 2, 2, _make_score_fn([{}, {}]))
    assert not result.feasible
    assert result.best is None
    assert "need at least 4" in result.explanation[0]


def test_deterministic_and_labeled():
    slots = [{"a": 8.0, "b": 9.0, "c": 1.0, "d": 2.0}, {"a": 1.0, "b": 2.0, "c": 8.0, "d": 9.0}]
    roster = ["a", "b", "c", "d"]
    first = optimize_team_allocation(roster, 2, 2, _make_score_fn(slots))
    second = optimize_team_allocation(roster, 2, 2, _make_score_fn(slots))
    assert first.best.assignment() == second.best.assignment()
    for team in first.best.teams:
        assert team["components"][0]["label"] == "HEURISTIC"
