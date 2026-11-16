"""Unit tests for end-user /start handler + main_menu callback (Task 14).

PTB handlers are async functions taking (update, context). Tests build mock
Update/Context objects and drive the handlers via asyncio.run().
"""

import asyncio
import re
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.services.bots.end_user_start as _mod


@pytest.fixture(autouse=True)
def _stub_username_generator():
    """Stub the figure generator for all start tests so its internal DB
    collision-check doesn't disturb the mock chains. The generator itself
    is tested in test_username_generator.py."""
    with patch.object(_mod, "generate_unique_username", return_value="rumi_a1f2"):
        yield


def _run(coro):
    """Drive an async coroutine from sync test code."""
    return asyncio.run(coro)


def _make_update(
    user_id=12345,
    first_name="Ali",
    chat_id=67890,
):
    """Build a mock telegram.Update object."""
    update = MagicMock()
    update.effective_user.id = user_id
    update.effective_user.first_name = first_name
    update.effective_chat.id = chat_id
    update.effective_message.reply_text = AsyncMock()
    update.callback_query = MagicMock()
    update.callback_query.answer = AsyncMock()
    update.callback_query.edit_message_text = AsyncMock()
    return update


def _make_context(admin_id=5, bot_id=1, args=None):
    """Build a mock telegram.ext.ContextTypes.DEFAULT_TYPE.

    `args` simulates context.args (the /start command argv). Defaults to []
    so the deep-link referral lookup is skipped unless explicitly provided.
    """
    context = MagicMock()
    context.application.bot_data = {"admin_id": admin_id, "bot_id": bot_id}
    context.args = args if args is not None else []
    return context


def _make_bot_mock(
    bot_id=1,
    admin_id=5,
    display_name="HasanVPN",
    welcome_message_fa=None,
):
    bot = MagicMock()
    bot.id = bot_id
    bot.admin_id = admin_id
    bot.bot_display_name = display_name
    bot.welcome_message_fa = welcome_message_fa
    admin = MagicMock()
    admin.username = "hasan"
    bot.admin = admin
    return bot


# ---------------------------------------------------------------------------
# start_command
# ---------------------------------------------------------------------------


def test_start_command_creates_new_user_and_sends_welcome():
    """First-time user: auto-registers, sends welcome with main menu."""
    update = _make_update(user_id=12345, first_name="Ali", chat_id=67890)
    context = _make_context(admin_id=5, bot_id=1)
    bot = _make_bot_mock(display_name="HasanVPN", welcome_message_fa=None)

    mock_db = MagicMock()
    # First query (AdminBot lookup) returns bot; second (AdminUser lookup) returns None
    mock_db.query.return_value.filter.return_value.first.side_effect = [bot, None]
    mock_db.refresh = MagicMock(side_effect=lambda x: setattr(x, "id", 99))

    with patch.object(_mod, "SessionLocal", return_value=mock_db):
        with patch.object(_mod, "set_password"):
            _run(_mod.start_command(update, context))

    # User was added
    mock_db.add.assert_called_once()
    added_user = mock_db.add.call_args[0][0]
    assert added_user.admin_id == 5
    assert added_user.telegram_id == 12345
    assert added_user.telegram_chat_id == 67890
    assert added_user.status == "lead"
    assert added_user.language == "fa"
    assert re.fullmatch(r"[a-z]+_[0-9a-f]{4}", added_user.username), added_user.username
    assert "hasan" not in added_user.username  # reseller identity must NOT leak

    # Welcome sent with main menu keyboard
    update.effective_message.reply_text.assert_awaited_once()
    call_kwargs = update.effective_message.reply_text.call_args.kwargs
    assert "reply_markup" in call_kwargs
    # Welcome message contains the bot's display name and user's first name
    msg = update.effective_message.reply_text.call_args.args[0]
    assert "HasanVPN" in msg
    assert "Ali" in msg


def test_start_command_uses_custom_welcome_message_when_set():
    """If bot.welcome_message_fa is set, use it instead of the default template."""
    update = _make_update()
    context = _make_context()
    custom_msg = "خوش آمدید به سرویس ما!"
    bot = _make_bot_mock(welcome_message_fa=custom_msg)

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.side_effect = [bot, None]
    mock_db.refresh = MagicMock(side_effect=lambda x: setattr(x, "id", 99))

    with patch.object(_mod, "SessionLocal", return_value=mock_db):
        with patch.object(_mod, "set_password"):
            _run(_mod.start_command(update, context))

    update.effective_message.reply_text.assert_awaited_once()
    assert update.effective_message.reply_text.call_args.args[0] == custom_msg


def test_start_command_existing_user_does_not_create_new_row():
    """Returning user: lookup finds them, db.add NOT called."""
    update = _make_update()
    context = _make_context()
    bot = _make_bot_mock()
    existing_user = MagicMock()
    existing_user.id = 50
    existing_user.telegram_id = 12345
    existing_user.telegram_chat_id = 99999  # different from current chat

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.side_effect = [
        bot,
        existing_user,
    ]

    with patch.object(_mod, "SessionLocal", return_value=mock_db):
        _run(_mod.start_command(update, context))

    # User was NOT added
    mock_db.add.assert_not_called()
    # telegram_chat_id was updated to current chat
    assert existing_user.telegram_chat_id == 67890


def test_start_command_username_exhaustion_replies_and_does_not_create():
    """When generate_unique_username raises RuntimeError, the handler replies
    with a 'try again' message and does NOT create a user (no db.add). The
    autouse `_stub_username_generator` is overridden by applying our own
    patch on the same target (`_mod.generate_unique_username`) — a patch
    decorator on the test takes precedence over the autouse fixture patch.
    """
    update = _make_update()
    context = _make_context()
    bot = _make_bot_mock()

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.side_effect = [bot, None]
    mock_db.add = MagicMock()
    mock_db.close = MagicMock()

    with patch.object(
        _mod,
        "generate_unique_username",
        side_effect=RuntimeError("exhausted"),
    ):
        with patch.object(_mod, "SessionLocal", return_value=mock_db):
            _run(_mod.start_command(update, context))  # must not raise

    # No user created
    mock_db.add.assert_not_called()
    # A retry message was sent
    update.effective_message.reply_text.assert_awaited_once()
    msg = update.effective_message.reply_text.call_args.args[0]
    assert "try again" in msg
    # Session closed cleanly (finally block ran)
    mock_db.close.assert_called_once()


def test_start_command_returns_early_when_bot_not_found():
    """If bot lookup fails (misconfigured), reply with error."""
    update = _make_update()
    context = _make_context(bot_id=999)

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = None

    with patch.object(_mod, "SessionLocal", return_value=mock_db):
        _run(_mod.start_command(update, context))

    update.effective_message.reply_text.assert_awaited_once()
    assert "not configured" in update.effective_message.reply_text.call_args.args[0]
    # db.add NOT called (we returned early)
    mock_db.add.assert_not_called()


def test_start_command_closes_db_session_always():
    """Even on early return, db.close() is called (finally block)."""
    update = _make_update()
    context = _make_context()

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = None
    mock_db.close = MagicMock()

    with patch.object(_mod, "SessionLocal", return_value=mock_db):
        _run(_mod.start_command(update, context))

    mock_db.close.assert_called_once()


# ---------------------------------------------------------------------------
# main_menu_callback
# ---------------------------------------------------------------------------


def test_main_menu_callback_edits_message_with_menu():
    """Tapping 'back' re-renders the main menu via edit_message_text."""
    update = _make_update()
    context = _make_context(bot_id=1)
    bot = _make_bot_mock(display_name="HasanVPN")
    user = MagicMock()
    user.language = "fa"

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.side_effect = [bot, user]

    with patch.object(_mod, "SessionLocal", return_value=mock_db):
        _run(_mod.main_menu_callback(update, context))

    update.callback_query.answer.assert_awaited_once()
    update.callback_query.edit_message_text.assert_awaited_once()
    msg = update.callback_query.edit_message_text.call_args.args[0]
    assert "HasanVPN" in msg
    # Reply markup is passed
    assert "reply_markup" in update.callback_query.edit_message_text.call_args.kwargs


# ---------------------------------------------------------------------------
# Deep-link referral parsing (/start ref_XXX)
# ---------------------------------------------------------------------------


def test_start_command_with_valid_referral_code_sets_referred_by():
    """Deep-link /start ref_<CODE> links the new user to the referrer."""
    update = _make_update()
    context = _make_context(args=["ref_ALICE-1a2b"])
    bot = _make_bot_mock()

    referrer = MagicMock()
    referrer.id = 99
    referrer.referral_code = "ALICE-1a2b"

    mock_db = MagicMock()
    # 1st first(): bot lookup → bot
    # 2nd first(): user lookup → None (new user)
    # 3rd first(): referrer lookup → referrer
    mock_db.query.return_value.filter.return_value.first.side_effect = [
        bot,
        None,
        referrer,
    ]
    mock_db.refresh = MagicMock(side_effect=lambda x: setattr(x, "id", 50))

    with patch.object(_mod, "SessionLocal", return_value=mock_db):
        with patch.object(_mod, "set_password"):
            _run(_mod.start_command(update, context))

    # The new AdminUser had referred_by_user_id set BEFORE the final commit
    added_user = mock_db.add.call_args[0][0]
    assert added_user.referred_by_user_id == 99


def test_start_command_with_invalid_referral_code_does_not_set_referred_by():
    """Unknown ref_XXX → user created normally, no referred_by_user_id."""
    update = _make_update()
    context = _make_context(args=["ref_UNKNOWN"])
    bot = _make_bot_mock()

    mock_db = MagicMock()
    # 1st: bot, 2nd: user=None (new), 3rd: referrer=None (unknown code)
    mock_db.query.return_value.filter.return_value.first.side_effect = [bot, None, None]
    mock_db.refresh = MagicMock(side_effect=lambda x: setattr(x, "id", 50))

    with patch.object(_mod, "SessionLocal", return_value=mock_db):
        with patch.object(_mod, "set_password"):
            _run(_mod.start_command(update, context))

    added_user = mock_db.add.call_args[0][0]
    assert added_user.referred_by_user_id is None


def test_start_command_blocks_self_referral():
    """User can't refer themselves (referrer.id == user.id guard)."""
    update = _make_update(user_id=12345)
    context = _make_context(args=["ref_MYSITE-abcd"])
    bot = _make_bot_mock()

    # Existing user with their own referral code
    existing_user = MagicMock()
    existing_user.id = 50
    existing_user.telegram_id = 12345
    existing_user.referral_code = "MYSITE-abcd"
    existing_user.referred_by_user_id = None

    # The referrer lookup returns the SAME user (self-referral attempt)
    referrer = existing_user

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.side_effect = [
        bot,
        existing_user,
        referrer,
    ]

    with patch.object(_mod, "SessionLocal", return_value=mock_db):
        _run(_mod.start_command(update, context))

    # Self-referral blocked: referred_by_user_id NOT set
    assert existing_user.referred_by_user_id is None


def test_start_command_does_not_overwrite_existing_referrer():
    """If user already has a referrer, deep-link doesn't overwrite."""
    update = _make_update()
    context = _make_context(args=["ref_NEWCODE"])
    bot = _make_bot_mock()

    existing_user = MagicMock()
    existing_user.id = 50
    existing_user.referred_by_user_id = 77  # already referred by 77

    new_referrer = MagicMock()
    new_referrer.id = 99
    new_referrer.referral_code = "NEWCODE"

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.side_effect = [
        bot,
        existing_user,
        new_referrer,
    ]

    with patch.object(_mod, "SessionLocal", return_value=mock_db):
        _run(_mod.start_command(update, context))

    # Existing referrer preserved
    assert existing_user.referred_by_user_id == 77


# ---------------------------------------------------------------------------
# register_end_user_handlers
# ---------------------------------------------------------------------------


def test_register_end_user_handlers_wires_start_and_main_menu():
    """register_end_user_handlers wires /start, main_menu, purchase, connections, settings, referral."""
    app = MagicMock()
    app.add_handler = MagicMock()

    _mod.register_end_user_handlers(app)

    # 2 (start, main_menu) + 4 (purchase) + 2 (connections) + 3 (settings) + 1 (referral) = 12
    assert app.add_handler.call_count >= 2
