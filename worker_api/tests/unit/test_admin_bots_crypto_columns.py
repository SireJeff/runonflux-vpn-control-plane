from app.models.admin_bots import AdminBot


def test_admin_bot_has_crypto_columns():
    cols = AdminBot.__table__.columns
    assert "crypto_address" in cols
    assert "crypto_network" in cols
    assert "crypto_memo" in cols
