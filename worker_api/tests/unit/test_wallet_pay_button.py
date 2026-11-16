from decimal import Decimal

from app.services.bots.end_user_purchase import can_pay_from_wallet


def test_shows_when_balance_covers_price():
    assert can_pay_from_wallet(Decimal("300000"), Decimal("300000")) is True


def test_hidden_when_insufficient():
    assert can_pay_from_wallet(Decimal("100000"), Decimal("300000")) is False
