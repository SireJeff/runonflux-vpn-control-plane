from app.models.wire_orders import WireOrder


def test_wire_order_has_crypto_columns():
    cols = WireOrder.__table__.columns
    assert "payment_method" in cols
    assert "crypto_txid" in cols
    assert "crypto_link" in cols
    assert "usd_rate_snapshot" in cols
    # default preserves existing rows as 'wire'
    assert cols["payment_method"].nullable is False
