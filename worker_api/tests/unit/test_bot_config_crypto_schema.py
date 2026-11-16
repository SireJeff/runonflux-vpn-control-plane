from app.schemas.bot_config import (
    BotConfigResponse,
    BotConfigUpdateRequest,
    BotConfigUpsertRequest,
)


def test_update_request_accepts_crypto_fields():
    req = BotConfigUpdateRequest(crypto_address="TABC", crypto_network="USDT (TRC20)")
    data = req.model_dump(exclude_unset=True)
    assert data == {"crypto_address": "TABC", "crypto_network": "USDT (TRC20)"}


def test_upsert_request_accepts_crypto_fields():
    req = BotConfigUpsertRequest(bot_token="x" * 20, crypto_memo="tag-1")
    assert req.crypto_memo == "tag-1"


def test_response_declares_crypto_fields():
    assert "crypto_address" in BotConfigResponse.model_fields
    assert "crypto_network" in BotConfigResponse.model_fields
    assert "crypto_memo" in BotConfigResponse.model_fields
