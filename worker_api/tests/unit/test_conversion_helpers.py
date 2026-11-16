from decimal import Decimal

from app.services.billing.conversion import tomans_to_usd, usd_to_tomans


def test_usd_to_tomans_rounds_to_whole():
    assert usd_to_tomans(Decimal("10"), Decimal("60000")) == Decimal("600000")
    assert usd_to_tomans(Decimal("1.005"), Decimal("60000")) == Decimal("60300")


def test_tomans_to_usd_quantizes_cents():
    assert tomans_to_usd(Decimal("600000"), Decimal("60000")) == Decimal("10.00")
    assert tomans_to_usd(Decimal("100000"), Decimal("60000")) == Decimal("1.67")
