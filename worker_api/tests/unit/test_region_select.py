"""Unit tests for the bidi-aware plan label builders."""

from decimal import Decimal
from unittest.mock import MagicMock

import app.services.bots.region_select as _mod

FSI, PDI, RLM = "⁨", "⁩", "‏"


def _pkg(name="Pro", gb=200.0, price=400000, all_regions=False):
    p = MagicMock()
    p.name = name
    p.traffic_limit_gb = Decimal(str(gb))
    p.price_tomans = Decimal(str(price))
    p.all_regions = all_regions
    return p


def test_button_label_is_rtl_data_driven_no_english_name():
    # Label is built from GB + price, NOT the reseller's English name.
    label = _mod.package_button_label(_pkg(name="Pro · 1mo", gb=200.0, price=400000))
    assert label.startswith(RLM)  # RTL base direction forced
    assert f"{FSI}200 گیگ{PDI}" in label  # GB+unit glued as one atom
    assert f"{FSI}400,000 ت{PDI}" in label  # price+unit glued as one atom
    assert "Pro" not in label  # English reseller name dropped


def test_button_label_all_regions_is_persian():
    label = _mod.package_button_label(
        _pkg(name="All Regions Monthly", all_regions=True)
    )
    assert "🌍" in label
    assert "همه مناطق" in label
    assert "All Regions" not in label  # English name dropped


def test_button_label_no_globe_for_single_region():
    assert "🌍" not in _mod.package_button_label(_pkg(all_regions=False))


def test_body_line_glues_each_field_and_drops_name():
    line = _mod.package_body_line(_pkg(name="Light · 1mo", gb=50.0, price=150000))
    assert f"{FSI}50 گیگ{PDI}" in line  # GB+unit one atom (cannot detach)
    assert f"{FSI}150,000 تومان{PDI}" in line  # price+unit one atom
    assert "Light" not in line  # English reseller name dropped
    assert line.startswith(RLM)  # forced RTL base
    assert "•" in line  # single-region marker


def test_body_line_all_regions_names_the_regions():
    line = _mod.package_body_line(_pkg(name="All Regions Monthly", all_regions=True))
    assert "🌍" in line
    assert "همه مناطق" in line
    for macro in ("اروپا", "آسیا", "آمریکا", "سایر"):
        assert macro in line  # covered regions enumerated
    assert "All Regions" not in line


def test_existing_region_helpers_still_present():
    assert _mod.required_region_count(2, False, ["eu", "as", "na"]) == 2
    assert _mod.can_confirm(["eu"], 1) is True
    assert not hasattr(_mod, "package_label")  # old builder removed
