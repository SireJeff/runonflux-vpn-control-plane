from app.services.bots.region_select import (
    can_confirm,
    required_region_count,
    toggle_region,
)


def test_required_count_fixed_plan():
    assert (
        required_region_count(
            region_count=2, all_regions=False, healthy=["eu", "as", "na"]
        )
        == 2
    )


def test_required_count_all_regions_is_all_healthy():
    assert (
        required_region_count(
            region_count=1, all_regions=True, healthy=["eu", "as", "na"]
        )
        == 3
    )


def test_required_count_graceful_degrade_when_short():
    # plan wants 3 but only 2 healthy -> require 2
    assert (
        required_region_count(region_count=3, all_regions=False, healthy=["eu", "as"])
        == 2
    )


def test_toggle_adds_and_removes():
    assert toggle_region(["eu"], "as", max_count=2) == ["eu", "as"]
    assert toggle_region(["eu", "as"], "eu", max_count=2) == ["as"]


def test_toggle_blocks_over_max():
    # already at max, toggling a new one is a no-op
    assert toggle_region(["eu", "as"], "na", max_count=2) == ["eu", "as"]


def test_can_confirm_requires_exact_count():
    assert can_confirm(["eu", "as"], required=2) is True
    assert can_confirm(["eu"], required=2) is False
