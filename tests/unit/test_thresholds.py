"""Resource threshold semantics (M12) — the full documented matrix + edge cases."""


from game_companion.core.resources.thresholds import (
    ResourceStatus,
    evaluate_resource_status,
)


def test_done_when_quantity_covers_planned_total():
    result = evaluate_resource_status(1200, single_max=400, planned_total=1200)
    assert result.status is ResourceStatus.DONE
    assert result.color == "white"
    assert "1200" in result.explanation


def test_prep_when_covers_one_max_but_not_all_planned():
    result = evaluate_resource_status(500, single_max=500, planned_total=1500)
    assert result.status is ResourceStatus.PREP
    assert result.color == "cyan/lime"


def test_very_low_band_between_fraction_and_single_max():
    result = evaluate_resource_status(200, single_max=500, planned_total=1500)
    assert result.status is ResourceStatus.VERY_LOW
    assert result.color == "orange"


def test_critically_low_below_fraction():
    result = evaluate_resource_status(100, single_max=500, planned_total=1500)
    assert result.status is ResourceStatus.CRITICALLY_LOW
    assert result.color == "red"


def test_unknown_when_no_requirements_known():
    result = evaluate_resource_status(42, single_max=None, planned_total=None)
    assert result.status is ResourceStatus.UNKNOWN
    assert result.color == "gray"
    assert "refusing to guess" in result.explanation


def test_unknown_quantity_with_plan_but_no_single_max_is_very_low():
    """Y known, X unknown: below plan can't be split into red/orange — report very_low."""
    result = evaluate_resource_status(100, single_max=None, planned_total=1000)
    assert result.status is ResourceStatus.VERY_LOW
    assert "cannot be distinguished" in result.explanation


def test_no_plan_defaults_to_single_character_target():
    # Y defaults to X: having a full single-max banked counts as done.
    assert evaluate_resource_status(500, single_max=500, planned_total=None).status is ResourceStatus.DONE
    assert evaluate_resource_status(499, single_max=500, planned_total=None).status is ResourceStatus.VERY_LOW


def test_negative_quantity_clamped():
    result = evaluate_resource_status(-5, single_max=500, planned_total=1500)
    assert result.quantity == 0
    assert result.status is ResourceStatus.CRITICALLY_LOW


def test_custom_low_fraction_config():
    result = evaluate_resource_status(200, single_max=500, planned_total=1500)
    # default fraction 0.25 -> 200 is very_low (>= 125)
    assert result.status is ResourceStatus.VERY_LOW


def test_exact_boundaries():
    # exactly at planned total -> done
    assert evaluate_resource_status(1000, single_max=400, planned_total=1000).status is ResourceStatus.DONE
    # exactly at single max (below plan) -> prep
    assert evaluate_resource_status(400, single_max=400, planned_total=1000).status is ResourceStatus.PREP
    # exactly at fraction line -> very_low
    assert evaluate_resource_status(100, single_max=400, planned_total=1000).status is ResourceStatus.VERY_LOW
