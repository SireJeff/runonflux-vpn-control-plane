"""Unit tests for end-user purchase flow (Task 15).

Drives async PTB handlers from sync test code via asyncio.run().
Uses the importlib pattern from test_end_user_start.py to load the module
without importing its heavy deps at collection time.
"""

import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram.ext import ApplicationHandlerStop

import app.services.bots.end_user_purchase as _mod


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Mock builders
# ---------------------------------------------------------------------------


def _make_update(user_id=12345, chat_id=67890, first_name="Ali"):
    """Build a mock Update with both callback_query and message paths."""
    update = MagicMock()
    update.effective_user.id = user_id
    update.effective_user.first_name = first_name
    update.effective_chat.id = chat_id
    update.effective_message.reply_text = AsyncMock()

    update.callback_query = MagicMock()
    update.callback_query.answer = AsyncMock()
    update.callback_query.edit_message_text = AsyncMock()
    update.callback_query.edit_message_reply_markup = AsyncMock()
    update.callback_query.data = "buy"

    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    update.message.photo = []
    return update


def _make_context(admin_id=5, bot_id=1):
    context = MagicMock()
    context.application.bot_data = {"admin_id": admin_id, "bot_id": bot_id}
    context.user_data = {}
    return context


def _make_package(
    id=10,
    name="Basic",
    traffic=20.0,
    duration=30,
    price=150000,
    display_order=1,
    all_regions=False,
):
    pkg = MagicMock()
    pkg.id = id
    pkg.name = name
    pkg.traffic_limit_gb = Decimal(str(traffic))
    pkg.duration_days = duration
    pkg.price_tomans = Decimal(str(price))
    pkg.display_order = display_order
    pkg.all_regions = all_regions
    pkg.region_count = 1
    pkg.is_active = True
    return pkg


def _make_bot(card_number="6037-9911-1234-5678", card_holder_name="Hasan Ali"):
    bot = MagicMock()
    bot.id = 1
    bot.admin_id = 5
    bot.card_number = card_number
    bot.card_holder_name = card_holder_name
    return bot


def _make_user(id=50, username="hasan_abc", wallet=Decimal("0")):
    user = MagicMock()
    user.id = id
    user.admin_id = 5
    user.username = username
    user.wallet_credit_tomans = wallet
    return user


def _make_order(id=100, amount=Decimal("150000"), snapshot=None, macro_region="eu"):
    order = MagicMock()
    order.id = id
    order.amount_tomans = amount
    order.package_snapshot = snapshot or {"name": "Basic"}
    order.macro_region = macro_region
    return order


# ---------------------------------------------------------------------------
# buy_callback
# ---------------------------------------------------------------------------


def test_buy_callback_shows_duration_menu():
    update = _make_update()
    update.callback_query.data = "buy"
    context = _make_context()

    # Two durations (30, 90) across three packages -> two duration buttons.
    pkgs = [
        _make_package(id=10, name="Light", duration=30, price=150000),
        _make_package(id=11, name="Plus", duration=30, price=250000),
        _make_package(id=20, name="Light", duration=90, price=400000),
    ]
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = (
        pkgs
    )

    with patch.object(_mod, "SessionLocal", return_value=mock_db):
        _run(_mod.buy_callback(update, context))

    update.callback_query.edit_message_text.assert_awaited_once()
    call = update.callback_query.edit_message_text.call_args
    text = call.args[0]
    keyboard = call.kwargs["reply_markup"].inline_keyboard

    assert "خرید اشتراک" in text
    assert "مدت اشتراک" in text
    dur_btns = [
        b.callback_data
        for row in keyboard
        for b in row
        if b.callback_data.startswith("dur:")
    ]
    assert dur_btns == ["dur:30", "dur:90"]  # ascending
    labels = [
        b.text for row in keyboard for b in row if b.callback_data.startswith("dur:")
    ]
    assert "1 ماهه" in labels[0]
    assert "3 ماهه" in labels[1]
    flat = [b.callback_data for row in keyboard for b in row]
    assert flat.count("main_menu") == 1  # nav_footer present
    mock_db.close.assert_called_once()


def test_buy_callback_single_duration_skips_to_plans():
    update = _make_update()
    update.callback_query.data = "buy"
    context = _make_context()

    pkgs = [
        _make_package(id=10, name="Light", duration=30, price=150000),
        _make_package(id=11, name="Plus", duration=30, price=250000),
    ]
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = (
        pkgs
    )

    with patch.object(_mod, "SessionLocal", return_value=mock_db):
        _run(_mod.buy_callback(update, context))

    text = update.callback_query.edit_message_text.call_args.args[0]
    keyboard = update.callback_query.edit_message_text.call_args.kwargs[
        "reply_markup"
    ].inline_keyboard
    # Straight to the plan list — pkg buttons, no dur buttons.
    pkg_btns = [
        b.callback_data
        for row in keyboard
        for b in row
        if b.callback_data.startswith("pkg:")
    ]
    assert pkg_btns == ["pkg:10", "pkg:11"]
    assert "پلن‌های" in text


def test_buy_callback_no_active_packages():
    update = _make_update()
    update.callback_query.data = "buy"
    context = _make_context()

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = (
        []
    )

    with patch.object(_mod, "SessionLocal", return_value=mock_db):
        _run(_mod.buy_callback(update, context))

    text = update.callback_query.edit_message_text.call_args.args[0]
    assert "هیچ پلنی موجود نیست" in text


def test_duration_callback_lists_only_that_durations_plans():
    update = _make_update()
    update.callback_query.data = "dur:90"
    context = _make_context()

    pkgs = [
        _make_package(id=10, name="Light", duration=30, price=150000),
        _make_package(id=20, name="Light", duration=90, price=400000),
        _make_package(id=21, name="Pro", duration=90, price=1100000),
        _make_package(
            id=22,
            name="All Regions Quarterly",
            duration=90,
            price=1900000,
            all_regions=True,
        ),
    ]
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = (
        pkgs
    )

    with patch.object(_mod, "SessionLocal", return_value=mock_db):
        _run(_mod.duration_callback(update, context))

    call = update.callback_query.edit_message_text.call_args
    text = call.args[0]
    keyboard = call.kwargs["reply_markup"].inline_keyboard

    assert "پلن‌های 3 ماهه" in text
    pkg_btns = [
        b.callback_data
        for row in keyboard
        for b in row
        if b.callback_data.startswith("pkg:")
    ]
    assert pkg_btns == ["pkg:20", "pkg:21", "pkg:22"]  # only 90-day plans
    # all-regions plan appears inline, badged 🌍 in body + button
    assert "🌍" in text
    all_btn = [b for row in keyboard for b in row if b.callback_data == "pkg:22"][0]
    assert "🌍" in all_btn.text
    # back-to-durations button reuses 'buy'
    flat = [b.callback_data for row in keyboard for b in row]
    assert "buy" in flat
    mock_db.close.assert_called_once()


def test_pgplans_callback_scoped_to_duration():
    update = _make_update()
    update.callback_query.data = "pgplans:30:1"
    context = _make_context()

    # 8 plans at 30 days -> 2 pages of 6; page 1 shows the last 2.
    pkgs = [
        _make_package(id=i, name=f"Plan{i}", duration=30, price=100000 + i)
        for i in range(8)
    ]
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = (
        pkgs
    )

    with patch.object(_mod, "SessionLocal", return_value=mock_db):
        _run(_mod.pgplans_callback(update, context))

    update.callback_query.edit_message_text.assert_awaited_once()
    keyboard = update.callback_query.edit_message_text.call_args.kwargs[
        "reply_markup"
    ].inline_keyboard
    pkg_btns = [
        b.callback_data
        for row in keyboard
        for b in row
        if b.callback_data.startswith("pkg:")
    ]
    assert pkg_btns == ["pkg:6", "pkg:7"]
    flat = [b.callback_data for row in keyboard for b in row]
    assert "pgplans:30:0" in flat  # prev-page arrow, scoped to duration 30
    mock_db.close.assert_called_once()


# ---------------------------------------------------------------------------
# package_callback
# ---------------------------------------------------------------------------


def test_package_callback_stores_id_and_shows_region_picker():
    update = _make_update()
    update.callback_query.data = "pkg:42"
    context = _make_context()

    pkg = _make_package(id=42)
    pkg.all_regions = False
    pkg.region_count = 1

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = pkg

    with patch.object(_mod, "SessionLocal", return_value=mock_db):
        with patch.object(
            _mod,
            "macro_region_availability",
            return_value=[{"code": "eu", "healthy_instances": 2}],
        ):
            with patch.object(_mod, "required_region_count", return_value=1):
                with patch.object(
                    _mod, "region_multiselect_keyboard", return_value=MagicMock()
                ):
                    _run(_mod.package_callback(update, context))

    assert context.user_data["picked_package_id"] == 42
    assert context.user_data["picked_regions"] == []
    update.callback_query.edit_message_text.assert_awaited_once()
    call = update.callback_query.edit_message_text.call_args
    assert "انتخاب منطقه" in call.args[0]
    assert "reply_markup" in call.kwargs


# ---------------------------------------------------------------------------
# _show_payment_instructions (card path) + region navigation
# ---------------------------------------------------------------------------


def test_show_payment_instructions_with_card():
    update = _make_update()
    context = _make_context()

    bot = _make_bot(card_number="6037-9911-1234-5678", card_holder_name="Hasan Ali")
    pkg = _make_package(id=10, name="Basic", traffic=20.0, duration=30, price=150000)

    mock_db = MagicMock()
    # _show_payment_instructions: AdminBot query, then _get_user query (None → no credit)
    mock_db.query.return_value.filter.return_value.first.side_effect = [bot, None]

    _run(_mod._show_payment_instructions(update, context, mock_db, pkg, ["eu"]))

    update.callback_query.edit_message_text.assert_awaited_once()
    text = update.callback_query.edit_message_text.call_args.args[0]

    assert "پرداخت" in text
    assert "Basic" in text
    assert "20" in text and "GB" in text  # GB run now isolated, not adjacent
    assert "روز" in text
    assert "EU" in text
    assert "150,000" in text
    assert "6037-9911-1234-5678" in text
    assert "Hasan Ali" in text
    assert "پس از پرداخت" in text


def test_show_payment_instructions_wallet_credit():
    update = _make_update()
    context = _make_context()

    bot = _make_bot()
    pkg = _make_package(id=10, name="Basic", price=150000)
    user = _make_user(wallet=Decimal("50000"))

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.side_effect = [bot, user]

    _run(_mod._show_payment_instructions(update, context, mock_db, pkg, ["as"]))

    text = update.callback_query.edit_message_text.call_args.args[0]
    assert "اعتبار کیف پول" in text
    assert "50,000" in text
    assert "100,000" in text  # 150000 - 50000


def test_show_payment_instructions_falls_back_when_no_card_number():
    update = _make_update()
    context = _make_context()

    bot = _make_bot(card_number=None, card_holder_name=None)
    pkg = _make_package(id=10, name="Basic", price=150000)

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.side_effect = [bot, None]

    _run(_mod._show_payment_instructions(update, context, mock_db, pkg, ["na"]))

    text = update.callback_query.edit_message_text.call_args.args[0]
    assert "کارتی ثبت نشده" in text


def test_region_toggle_session_expired():
    update = _make_update()
    update.callback_query.data = "rtoggle:eu"
    context = _make_context()
    # user_data empty — no region_required (session expired)

    _run(_mod.region_toggle_callback(update, context))

    text = update.callback_query.edit_message_text.call_args.args[0]
    assert "منقضی شده" in text


def test_show_payment_instructions_handles_missing_bot():
    update = _make_update()
    context = _make_context()

    pkg = _make_package(id=10, name="Basic", price=150000)
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = None  # bot None

    _run(_mod._show_payment_instructions(update, context, mock_db, pkg, ["eu"]))

    text = update.callback_query.edit_message_text.call_args.args[0]
    assert "خطا" in text


# ---------------------------------------------------------------------------
# receipt_photo_handler
# ---------------------------------------------------------------------------


def _setup_receipt_test(user, pending_count=0):
    """Shared setup for receipt_photo_handler tests."""
    update = _make_update(user_id=12345)
    photo = MagicMock()
    photo.file_id = "file_abc"
    photo.file_unique_id = "unique_abc"
    update.message.photo = [MagicMock(), photo]  # [-1] is highest-res

    context = _make_context(admin_id=5)
    context.user_data["picked_package_id"] = 10
    context.user_data["picked_regions"] = ["eu"]

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = user
    mock_db.query.return_value.filter.return_value.count.return_value = pending_count
    return update, context, mock_db


def test_receipt_photo_handler_creates_order_and_notifies_admin():
    user = _make_user(id=50, username="hasan_abc")
    order = _make_order(id=100, amount=Decimal("150000"), macro_region="eu")
    update, context, mock_db = _setup_receipt_test(user, pending_count=0)

    mock_os = MagicMock()
    mock_os.create_order.return_value = order
    mock_router = MagicMock()

    with patch.object(_mod, "SessionLocal", return_value=mock_db):
        with patch.object(_mod, "OrderService", return_value=mock_os):
            with patch.object(_mod, "NotificationRouter", return_value=mock_router):
                with patch.object(
                    _mod, "format_admin_new_receipt", return_value="ADMIN_MSG"
                ):
                    with patch.object(
                        _mod, "format_user_receipt_received", return_value="USER_MSG"
                    ):
                        with patch.object(
                            _mod, "_bot_token_for_admin", return_value="TOKEN"
                        ):
                            # _safe_download_and_persist is async — patch it to a sync MagicMock
                            # so asyncio.create_task receives a known value.
                            with patch.object(
                                _mod,
                                "_safe_download_and_persist",
                                new_callable=MagicMock,
                                return_value="CORO",
                            ) as mock_safe:
                                with patch.object(_mod, "asyncio") as mock_asyncio:
                                    _run(_mod.receipt_photo_handler(update, context))

    # Order created with the right args
    mock_os.create_order.assert_called_once()
    kwargs = mock_os.create_order.call_args.kwargs
    assert kwargs["user"] == user
    assert kwargs["package_id"] == 10
    assert kwargs["macro_regions"] == ["eu"]
    assert kwargs["receipt_file_id"] == "file_abc"
    assert kwargs["receipt_file_unique_id"] == "unique_abc"

    # User got receipt-received reply
    update.effective_message.reply_text.assert_awaited_once_with("USER_MSG")

    # Admin got notification
    mock_router.send_to_admin.assert_called_once_with(5, "ADMIN_MSG")

    # Receipt download scheduled
    mock_asyncio.create_task.assert_called_once_with("CORO")
    mock_safe.assert_called_once_with("TOKEN", "file_abc", 100)

    # user_data cleared
    assert "picked_package_id" not in context.user_data
    assert "picked_regions" not in context.user_data
    mock_db.close.assert_called_once()


def test_receipt_photo_handler_rejects_when_no_active_flow():
    """User uploaded a photo without picking package+region first."""
    update = _make_update()
    update.message.photo = [MagicMock()]
    context = _make_context()
    # No picked_package_id / picked_region in user_data

    _run(_mod.receipt_photo_handler(update, context))

    update.effective_message.reply_text.assert_awaited_once()
    text = update.effective_message.reply_text.call_args.args[0]
    assert "خرید اشتراک" in text


def test_receipt_photo_handler_rate_limits_at_three_pending():
    user = _make_user(id=50)
    update, context, mock_db = _setup_receipt_test(user, pending_count=3)

    with patch.object(_mod, "SessionLocal", return_value=mock_db):
        _run(_mod.receipt_photo_handler(update, context))

    text = update.effective_message.reply_text.call_args.args[0]
    assert "۳ سفارش" in text or "3 سفارش" in text


def test_receipt_photo_handler_user_not_found():
    update, context, mock_db = _setup_receipt_test(user=None)

    with patch.object(_mod, "SessionLocal", return_value=mock_db):
        _run(_mod.receipt_photo_handler(update, context))

    text = update.effective_message.reply_text.call_args.args[0]
    assert "کاربر یافت نشد" in text


def test_receipt_photo_handler_skips_download_when_no_bot_token():
    """If _bot_token_for_admin returns None, asyncio.create_task not called."""
    user = _make_user(id=50)
    order = _make_order(id=200)
    update, context, mock_db = _setup_receipt_test(user, pending_count=0)

    mock_os = MagicMock()
    mock_os.create_order.return_value = order
    mock_router = MagicMock()

    with patch.object(_mod, "SessionLocal", return_value=mock_db):
        with patch.object(_mod, "OrderService", return_value=mock_os):
            with patch.object(_mod, "NotificationRouter", return_value=mock_router):
                with patch.object(_mod, "format_admin_new_receipt", return_value="A"):
                    with patch.object(
                        _mod, "format_user_receipt_received", return_value="U"
                    ):
                        with patch.object(
                            _mod, "_bot_token_for_admin", return_value=None
                        ):
                            with patch.object(_mod, "asyncio") as mock_asyncio:
                                _run(_mod.receipt_photo_handler(update, context))

    mock_asyncio.create_task.assert_not_called()
    # State still cleared
    assert "picked_package_id" not in context.user_data


# ---------------------------------------------------------------------------
# crypto_txid_handler
# ---------------------------------------------------------------------------


def _setup_crypto_txid_test(user, pending_count=0):
    """Shared setup for crypto_txid_handler tests (mirrors _setup_receipt_test)."""
    update = _make_update(user_id=12345)
    update.message.text = "some-tx-id-123"

    context = _make_context(admin_id=5)
    context.user_data["awaiting_crypto_txid"] = True
    context.user_data["picked_package_id"] = 10
    context.user_data["picked_regions"] = ["eu"]

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = user
    mock_db.query.return_value.filter.return_value.count.return_value = pending_count
    return update, context, mock_db


def test_crypto_txid_handler_rate_limits_at_three_pending():
    user = _make_user(id=50)
    update, context, mock_db = _setup_crypto_txid_test(user, pending_count=3)

    mock_os = MagicMock()
    mock_router = MagicMock()

    with patch.object(_mod, "SessionLocal", return_value=mock_db):
        with patch.object(_mod, "OrderService", return_value=mock_os):
            with patch.object(_mod, "NotificationRouter", return_value=mock_router):
                with pytest.raises(ApplicationHandlerStop):
                    _run(_mod.crypto_txid_handler(update, context))

    # No order created — throttle short-circuited before create_order
    mock_os.create_order.assert_not_called()

    # User was told about the pending-order limit
    update.message.reply_text.assert_awaited_once()
    text = update.message.reply_text.call_args.args[0]
    assert "۳ سفارش" in text or "3 سفارش" in text

    # awaiting flag cleared so the next text message isn't mistaken for a txid
    assert context.user_data["awaiting_crypto_txid"] is False

    mock_db.close.assert_called_once()


# ---------------------------------------------------------------------------
# register
# ---------------------------------------------------------------------------


def test_receipt_download_failure_logs_exception():
    """When _safe_download_and_persist runs and download_and_store raises,
    logger.exception is called with the order_id."""
    with patch.object(
        _mod,
        "download_and_store",
        new_callable=AsyncMock,
        side_effect=RuntimeError("timeout"),
    ):
        with patch.object(_mod, "persist_path") as mock_persist:
            with patch.object(_mod, "logger") as mock_logger:
                _run(_mod._safe_download_and_persist("TOKEN", "file_abc", 100))

    mock_logger.exception.assert_called_once_with(
        "Receipt download failed for order %s",
        100,
    )
    mock_persist.assert_not_called()


def test_receipt_download_success_persists_path():
    """When download_and_store succeeds, persist_path is called."""
    with patch.object(
        _mod,
        "download_and_store",
        new_callable=AsyncMock,
        return_value="/data/receipts/100.jpg",
    ):
        with patch.object(_mod, "persist_path") as mock_persist:
            with patch.object(_mod, "logger"):
                _run(_mod._safe_download_and_persist("TOKEN", "file_abc", 100))

    mock_persist.assert_called_once_with(100, "/data/receipts/100.jpg")


def test_register_adds_nine_handlers():
    app = MagicMock()
    _mod.register(app)
    assert app.add_handler.call_count == 9
