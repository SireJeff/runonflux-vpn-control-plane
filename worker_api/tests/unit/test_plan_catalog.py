"""Unit tests for duration-based plan grouping."""

from unittest.mock import MagicMock

import app.services.bots.plan_catalog as _mod


def _pkg(pid, days):
    p = MagicMock()
    p.id = pid
    p.duration_days = days
    return p


def test_groups_by_distinct_duration_sorted_ascending():
    pkgs = [_pkg(1, 90), _pkg(2, 30), _pkg(3, 90), _pkg(4, 365)]
    groups = _mod.group_by_duration(pkgs)
    assert [g.duration_days for g in groups] == [30, 90, 365]


def test_group_preserves_input_order_within_bucket():
    pkgs = [_pkg(1, 30), _pkg(2, 30), _pkg(3, 30)]
    groups = _mod.group_by_duration(pkgs)
    assert len(groups) == 1
    assert [p.id for p in groups[0].packages] == [1, 2, 3]


def test_empty_list_yields_no_groups():
    assert _mod.group_by_duration([]) == []


def test_duration_label_months():
    assert _mod.duration_label(30) == "1 ماهه"
    assert _mod.duration_label(90) == "3 ماهه"
    assert _mod.duration_label(180) == "6 ماهه"
    assert _mod.duration_label(365) == "12 ماهه"


def test_duration_label_sub_month_fallback():
    assert _mod.duration_label(7) == "7 روزه"
