"""Unit tests for the bidi (RTL) readability helpers."""

import app.services.bots.bidi_fa as _mod

FSI, PDI, RLM = "⁨", "⁩", "‏"


def test_num_wraps_in_isolates_with_separator():
    assert _mod.num(150000) == f"{FSI}150,000{PDI}"


def test_num_accepts_str_and_decimal_like():
    assert _mod.num("50") == f"{FSI}50{PDI}"


def test_num_keeps_digits_contiguous_inside_isolates():
    # The digit run stays a single contiguous block so it cannot be split /
    # reordered by the bidi algorithm.
    out = _mod.num(400000)
    assert "400,000" in out
    assert out.startswith(FSI) and out.endswith(PDI)


def test_ltr_wraps_latin_token():
    assert _mod.ltr("Pro") == f"{FSI}Pro{PDI}"


def test_rtl_line_prefixes_rlm():
    assert _mod.rtl_line("Pro") == f"{RLM}Pro"


def test_num_unit_glues_number_and_unit_in_one_isolate():
    # The whole "30 گیگ" is one FSI…PDI atom -> number cannot detach from unit.
    assert _mod.num_unit(30, "گیگ") == f"{FSI}30 گیگ{PDI}"


def test_num_unit_thousands_separator_and_single_isolate():
    out = _mod.num_unit(100000, "تومان")
    assert out == f"{FSI}100,000 تومان{PDI}"
    assert out.count(FSI) == 1 and out.count(PDI) == 1


def test_num_unit_two_fields_stay_separable_atoms():
    # Two isolated field-atoms in one line: each is contiguous, neither leaks.
    line = f"• {_mod.num_unit(50, 'گیگ')} — {_mod.num_unit(150000, 'تومان')}"
    assert f"{FSI}50 گیگ{PDI}" in line
    assert f"{FSI}150,000 تومان{PDI}" in line


def test_num_embedded_midphrase_stays_wrapped():
    # Regression guard for "the number jumps to the end of the phrase":
    # the isolated run appears exactly where composed, not at a boundary.
    line = f"مبلغ: {_mod.num(250000)} تومان"
    assert line == f"مبلغ: {FSI}250,000{PDI} تومان"
