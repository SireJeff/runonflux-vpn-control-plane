from decimal import Decimal

from app.services.notifications import templates_en, templates_fa


def test_fa_topup_approved_mentions_amount_and_balance():
    s = templates_fa.format_wallet_topup_approved(Decimal("200000"), Decimal("350000"))
    assert "200,000" in s and "350,000" in s


def test_en_topup_approved_mentions_amount():
    s = templates_en.format_wallet_topup_approved(Decimal("200000"), Decimal("350000"))
    assert "200,000" in s


def test_wallet_screen_renders_balance():
    s = templates_fa.format_wallet_screen(Decimal("120000"), [])
    assert "120,000" in s
