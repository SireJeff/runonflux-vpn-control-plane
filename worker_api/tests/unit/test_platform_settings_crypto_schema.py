from app.schemas.super_admin import PlatformSettingsResponse, UpdateSettingsRequest


def test_settings_response_has_crypto_fields():
    resp = PlatformSettingsResponse(
        price_per_gb="0",
        price_per_region_monthly="0",
        min_topup_tomans="0",
        toman_to_usd_rate="0",
        toman_per_usd_rate="60000",
        crypto_topup_address="TXYZ...",
        crypto_topup_network="USDT (TRC20)",
        crypto_topup_memo="",
        min_topup_usd="10",
    )
    assert resp.crypto_topup_address == "TXYZ..."
    assert resp.min_topup_usd == "10"


def test_update_settings_accepts_crypto_fields():
    req = UpdateSettingsRequest(crypto_topup_address="TABC", min_topup_usd="25")
    data = req.model_dump(exclude_unset=True)
    assert data == {"crypto_topup_address": "TABC", "min_topup_usd": "25"}
