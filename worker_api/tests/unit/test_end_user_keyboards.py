"""Tests for nav_footer() and main_menu(lang) bilingual helpers."""

import app.services.bots.end_user_keyboards as _mod


def _callbacks(markup) -> list:
    """Flatten an InlineKeyboardMarkup into a list of callback_data strings."""
    out = []
    for row in markup.inline_keyboard:
        for btn in row:
            out.append(btn.callback_data)
    return out


def test_main_menu_fa_has_six_callbacks():
    cbs = _callbacks(_mod.main_menu("fa"))
    assert set(cbs) == {
        "buy",
        "my_sub",
        "connections",
        "support",
        "referral",
        "settings",
    }


def test_main_menu_en_labels_are_english():
    markup = _mod.main_menu("en")
    labels = [btn.text for row in markup.inline_keyboard for btn in row]
    assert any("Buy" in t for t in labels)
    assert any("My Subscription" in t for t in labels)


def test_nav_footer_home_always_present():
    row = _mod.nav_footer("fa")[0]
    assert any(b.callback_data == "main_menu" for b in row)


def test_nav_footer_back_only_when_provided():
    assert _mod.nav_footer("fa")[0][0].callback_data == "main_menu"  # no back
    row = _mod.nav_footer("fa", back_to="connections")[0]
    assert row[0].callback_data == "connections"  # back first
    assert row[-1].callback_data == "main_menu"  # home is last when no quick_switch


def test_nav_footer_quick_switch_bilingual():
    row_fa = _mod.nav_footer("fa", quick_switch="connections")[0]
    row_en = _mod.nav_footer("en", quick_switch="connections")[0]
    assert any("اتصالات" in b.text for b in row_fa)
    assert any("My Connections" in b.text for b in row_en)


def test_main_menu_fa_alias_still_works():
    assert _callbacks(_mod.main_menu_fa()) == _callbacks(_mod.main_menu("fa"))


def test_nav_footer_back_and_quick_switch_both_set():
    """When both back_to and quick_switch are given, order is [back, home, switch]."""
    row = _mod.nav_footer("fa", back_to="connections", quick_switch="my_sub")[0]
    assert [b.callback_data for b in row] == ["connections", "main_menu", "my_sub"]


def test_nav_footer_non_root_has_back_and_home():
    rows = _mod.nav_footer("en", screen="plans")  # parent = buy
    cbs = [b.callback_data for r in rows for b in r]
    assert "buy" in cbs  # Back -> parent
    assert "main_menu" in cbs  # Home


def test_nav_footer_uses_english_labels():
    rows = _mod.nav_footer("en", screen="plans")
    texts = [b.text for r in rows for b in r]
    assert any("Back" in t for t in texts)
    assert any("Main Menu" in t for t in texts)
