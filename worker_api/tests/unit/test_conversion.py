"""Parity tests for the canonical Toman/USD conversion helpers (issue #40).

Locks in ROUND_HALF_UP semantics: a bare Decimal.quantize() defaults to
banker's rounding (ROUND_HALF_EVEN), which diverges from these helpers on
exact half-unit ties.
"""

from decimal import Decimal

from app.services.billing.conversion import tomans_to_usd, usd_to_tomans


def test_usd_to_tomans_rounds_half_up():
    # 0.5-Toman tie must round UP (banker's would give 0)
    assert usd_to_tomans(Decimal("0.5"), Decimal("1")) == Decimal("1")
    # 2.5 tie -> 3 (banker's would give 2)
    assert usd_to_tomans(Decimal("2.5"), Decimal("1")) == Decimal("3")


def test_tomans_to_usd_rounds_half_up():
    # 5 / 2 = 2.5 exactly -> quantized to 0.01 has no tie here, but the
    # division itself lands on an exact half-cent boundary once quantized:
    # 5/2 = 2.50 (exact, no rounding needed) - use a genuine half-cent tie
    # instead: 1 / 8 = 0.125 -> ties at the third decimal, rounds to 0.13
    # (banker's would give 0.12 since 2 is even).
    assert tomans_to_usd(Decimal("1"), Decimal("8")) == Decimal("0.13")
