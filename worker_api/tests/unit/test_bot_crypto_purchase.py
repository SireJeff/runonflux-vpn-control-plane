import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram.ext import ApplicationHandlerStop

from app.services.bots import end_user_purchase as ep
from app.services.orders.order_service import OrderError


def test_module_exposes_crypto_handlers():
    assert hasattr(ep, "paymethod_callback")
    assert hasattr(ep, "crypto_txid_handler")
    assert hasattr(ep, "_show_crypto_instructions")


def test_render_crypto_instructions_text_includes_address_and_usd():
    # Pure text builder: (address, network, memo, amount_tomans, rate) -> str
    text = ep._crypto_instructions_text(
        address="TWALLET123",
        network="USDT (TRC20)",
        memo="tag-9",
        amount_tomans=3000000,
        rate=60000,
    )
    assert "TWALLET123" in text
    assert "USDT (TRC20)" in text
    assert "tag-9" in text
    assert "50" in text  # 3,000,000 / 60,000 USD


@pytest.mark.asyncio
async def test_crypto_txid_handler_replies_friendly_on_order_error():
    """If the reseller removes their crypto address mid-purchase, create_order
    raises OrderError; the handler must reply (in Persian), clear the awaiting
    flag, stop propagation, and NOT notify the admin."""
    # --- context / update doubles ---
    tg_message = MagicMock()
    tg_message.text = "0xdeadbeef"
    tg_message.reply_text = AsyncMock()

    update = MagicMock()
    update.message = tg_message
    update.effective_user = types.SimpleNamespace(id=555)

    context = MagicMock()
    context.application.bot_data = {"admin_id": 1}
    context.user_data = {
        "awaiting_crypto_txid": True,
        "picked_package_id": 1,
        "picked_regions": ["eu"],
    }

    fake_db = MagicMock()
    # pending_count query -> 0 (below the >=3 throttle)
    fake_db.query.return_value.filter.return_value.count.return_value = 0
    fake_user = types.SimpleNamespace(id=99, username="u1", language="fa")

    with patch.object(ep, "SessionLocal", return_value=fake_db), patch.object(
        ep, "_get_user", return_value=fake_user
    ), patch.object(ep, "OrderService") as mock_order_service, patch.object(
        ep, "NotificationRouter"
    ) as mock_router:
        mock_order_service.return_value.create_order.side_effect = OrderError(
            "Crypto payments are not enabled for this reseller"
        )

        with pytest.raises(ApplicationHandlerStop):
            await ep.crypto_txid_handler(update, context)

    # replied to the user (Persian content — assert a reply happened, not the card success template)
    assert tg_message.reply_text.await_count == 1
    reply_text_arg = tg_message.reply_text.await_args.args[0]
    assert isinstance(reply_text_arg, str) and reply_text_arg.strip()
    # awaiting flag cleared so the next text message is not swallowed
    assert context.user_data.get("awaiting_crypto_txid") is not True
    # admin was NOT notified about a non-existent order
    mock_router.return_value.send_to_admin.assert_not_called()
