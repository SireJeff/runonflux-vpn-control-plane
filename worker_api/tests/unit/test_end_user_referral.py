"""Unit tests for end-user referral view (Task 18)."""

import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import app.services.bots.end_user_referral as _mod


def _run(coro):
    return asyncio.run(coro)


def _make_update(user_id=12345):
    update = MagicMock()
    update.effective_user.id = user_id
    update.callback_query = MagicMock()
    update.callback_query.answer = AsyncMock()
    update.callback_query.edit_message_text = AsyncMock()
    return update


def _make_context(admin_id=5, bot_id=1):
    context = MagicMock()
    context.application.bot_data = {"admin_id": admin_id, "bot_id": bot_id}
    return context


def _make_config(reward_pct=Decimal("10.00")):
    cfg = MagicMock()
    cfg.is_enabled = True
    cfg.reward_percentage = reward_pct
    return cfg


def _make_user(id=50, referral_code=None, wallet=Decimal("0")):
    user = MagicMock()
    user.id = id
    user.admin_id = 5
    user.referral_code = referral_code
    user.wallet_credit_tomans = wallet
    return user


def _make_bot(username="hasanbot"):
    bot = MagicMock()
    bot.id = 1
    bot.bot_username = username
    return bot


# ---------------------------------------------------------------------------
# referral_callback
# ---------------------------------------------------------------------------


def test_referral_disabled_config_shows_disabled_message():
    update = _make_update()
    context = _make_context()

    mock_db = MagicMock()
    # First query: AdminReferralConfig lookup → None (disabled)
    mock_db.query.return_value.filter.return_value.first.return_value = None

    with patch.object(_mod, "SessionLocal", return_value=mock_db):
        _run(_mod.referral_callback(update, context))

    text = update.callback_query.edit_message_text.call_args.args[0]
    assert "غیرفعال" in text


def test_referral_user_without_referral_code_shows_buy_first():
    """User hasn't purchased yet → no referral code → friendly prompt."""
    update = _make_update()
    context = _make_context()
    cfg = _make_config()
    user = _make_user(referral_code=None)

    mock_db = MagicMock()
    # 1st first() → cfg, 2nd first() → user (no referral_code)
    mock_db.query.return_value.filter.return_value.first.side_effect = [cfg, user]

    with patch.object(_mod, "SessionLocal", return_value=mock_db):
        _run(_mod.referral_callback(update, context))

    text = update.callback_query.edit_message_text.call_args.args[0]
    assert "خریداری کنید" in text


def test_referral_user_not_found_shows_buy_first():
    """If user lookup fails, treat like 'no sub yet'."""
    update = _make_update()
    context = _make_context()
    cfg = _make_config()

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.side_effect = [cfg, None]

    with patch.object(_mod, "SessionLocal", return_value=mock_db):
        _run(_mod.referral_callback(update, context))

    text = update.callback_query.edit_message_text.call_args.args[0]
    assert "خریداری کنید" in text


def test_referral_happy_path_shows_code_earnings_wallet_share_link():
    update = _make_update()
    context = _make_context()
    cfg = _make_config(reward_pct=Decimal("15.00"))
    user = _make_user(
        id=50,
        referral_code="ALICE-1a2b",
        wallet=Decimal("25000"),
    )
    bot = _make_bot(username="hasanbot")

    mock_db = MagicMock()
    # Query sequence:
    #   1) AdminReferralConfig.first() → cfg
    #   2) AdminUser.first() → user
    #   3) sum(amount_tomans).scalar() → 50000 (total earned)
    #   4) AdminBot.first() → bot
    mock_db.query.return_value.filter.return_value.first.side_effect = [cfg, user, bot]
    # scalar() is on a different chain: query().filter().scalar()
    mock_db.query.return_value.filter.return_value.scalar.return_value = Decimal(
        "50000"
    )

    with patch.object(_mod, "SessionLocal", return_value=mock_db):
        _run(_mod.referral_callback(update, context))

    call = update.callback_query.edit_message_text.call_args
    text = call.args[0]
    keyboard = call.kwargs["reply_markup"].inline_keyboard

    assert "ALICE-1a2b" in text
    assert "50,000" in text  # total earned
    assert "25,000" in text  # wallet
    assert "15%" in text  # reward pct
    assert "https://t.me/hasanbot?start=ref_ALICE-1a2b" in text

    # Share button + back button
    assert len(keyboard) == 2
    share_btn = keyboard[0][0]
    assert "اشتراک" in share_btn.text
    assert share_btn.url == "https://t.me/hasanbot?start=ref_ALICE-1a2b"
    assert keyboard[1][0].callback_data == "main_menu"


def test_referral_zero_earnings_renders_zero():
    """Newly-activated user with no referrals yet: 0 toman earned."""
    update = _make_update()
    context = _make_context()
    cfg = _make_config()
    user = _make_user(id=50, referral_code="ALICE-1a2b", wallet=Decimal("0"))
    bot = _make_bot()

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.side_effect = [cfg, user, bot]
    mock_db.query.return_value.filter.return_value.scalar.return_value = 0

    with patch.object(_mod, "SessionLocal", return_value=mock_db):
        _run(_mod.referral_callback(update, context))

    text = update.callback_query.edit_message_text.call_args.args[0]
    assert "0" in text  # zero earnings


# ---------------------------------------------------------------------------
# register
# ---------------------------------------------------------------------------


def test_register_adds_one_handler():
    app = MagicMock()
    _mod.register(app)
    assert app.add_handler.call_count == 1
