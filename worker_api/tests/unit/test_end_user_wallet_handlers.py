from decimal import Decimal

import pytest

from app.services.bots.end_user_wallet import parse_topup_amount


def test_parse_valid_amount():
    assert parse_topup_amount("200000", Decimal("100000")) == Decimal("200000")


def test_parse_below_min_raises():
    with pytest.raises(ValueError):
        parse_topup_amount("50000", Decimal("100000"))


def test_parse_non_numeric_raises():
    with pytest.raises(ValueError):
        parse_topup_amount("abc", Decimal("100000"))


def test_parse_strips_separators():
    assert parse_topup_amount("۲۰۰,۰۰۰", Decimal("100000")) == Decimal("200000")
