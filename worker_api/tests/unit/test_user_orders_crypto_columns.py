from app.models.user_orders import UserOrder


def test_user_order_has_crypto_columns():
    cols = UserOrder.__table__.columns
    assert "payment_method" in cols
    assert "crypto_txid" in cols
    assert "crypto_link" in cols
    assert "amount_usd_snapshot" in cols
    assert cols["payment_method"].nullable is False
