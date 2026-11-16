"""Unit tests for Settings + Support handlers (Task 17)."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import app.services.bots.end_user_settings as _mod


def _run(coro):
    return asyncio.run(coro)


def _make_update(user_id=12345, callback_data="settings"):
    update = MagicMock()
    update.effective_user.id = user_id
    update.callback_query = MagicMock()
    update.callback_query.answer = AsyncMock()
    update.callback_query.edit_message_text = AsyncMock()
    update.callback_query.data = callback_data
    return update


def _make_context(admin_id=5, bot_id=1):
    context = MagicMock()
    context.application.bot_data = {"admin_id": admin_id, "bot_id": bot_id}
    return context


def _make_user(id=50, language="fa"):
    user = MagicMock()
    user.id = id
    user.admin_id = 5
    user.language = language
    return user


def _make_bot(support_telegram=None, support_phone=None):
    bot = MagicMock()
    bot.id = 1
    bot.support_telegram = support_telegram
    bot.support_phone = support_phone
    return bot


# ---------------------------------------------------------------------------
# settings_callback
# ---------------------------------------------------------------------------


def test_settings_callback_shows_language_picker():
    update = _make_update(callback_data="settings")
    context = _make_context()

    _run(_mod.settings_callback(update, context))

    update.callback_query.edit_message_text.assert_awaited_once()
    call = update.callback_query.edit_message_text.call_args
    assert "تنظیمات" in call.args[0]
    assert "reply_markup" in call.kwargs
    # language_picker has fa + en buttons
    keyboard = call.kwargs["reply_markup"].inline_keyboard
    flat = [btn.callback_data for row in keyboard for btn in row]
    assert "lang:fa" in flat
    assert "lang:en" in flat
    assert "main_menu" in flat


# ---------------------------------------------------------------------------
# lang_callback
# ---------------------------------------------------------------------------


def test_lang_callback_persists_fa_and_returns_to_main_menu():
    update = _make_update(callback_data="lang:fa")
    context = _make_context()
    user = _make_user(language="en")  # currently en, switching to fa

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = user

    with patch.object(_mod, "SessionLocal", return_value=mock_db):
        _run(_mod.lang_callback(update, context))

    assert user.language == "fa"
    mock_db.commit.assert_called_once()

    update.callback_query.edit_message_text.assert_awaited_once()
    call = update.callback_query.edit_message_text.call_args
    assert "فارسی" in call.args[0]
    # Main menu keyboard returned
    assert "reply_markup" in call.kwargs


def test_lang_callback_persists_en():
    update = _make_update(callback_data="lang:en")
    context = _make_context()
    user = _make_user(language="fa")

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = user

    with patch.object(_mod, "SessionLocal", return_value=mock_db):
        _run(_mod.lang_callback(update, context))

    assert user.language == "en"
    text = update.callback_query.edit_message_text.call_args.args[0]
    assert "English" in text


def test_lang_callback_user_not_found_does_not_raise():
    """Edge case: user somehow not in DB — commit not called, no crash."""
    update = _make_update(callback_data="lang:fa")
    context = _make_context()

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = None

    with patch.object(_mod, "SessionLocal", return_value=mock_db):
        _run(_mod.lang_callback(update, context))

    mock_db.commit.assert_not_called()
    # Still replies with the confirmation
    update.callback_query.edit_message_text.assert_awaited_once()


# ---------------------------------------------------------------------------
# support_callback
# ---------------------------------------------------------------------------


def test_support_callback_shows_telegram_and_phone():
    update = _make_update(callback_data="support")
    context = _make_context()
    bot = _make_bot(support_telegram="support.example.invalid", support_phone="+12025550123")

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = bot

    with patch.object(_mod, "SessionLocal", return_value=mock_db):
        _run(_mod.support_callback(update, context))

    text = update.callback_query.edit_message_text.call_args.args[0]
    assert "@support.example.invalid" in text
    assert "+12025550123" in text
    markup = update.callback_query.edit_message_text.call_args.kwargs["reply_markup"]
    cbs = [b.callback_data for row in markup.inline_keyboard for b in row]
    assert "main_menu" in cbs


def test_support_callback_shows_only_telegram_when_no_phone():
    update = _make_update(callback_data="support")
    context = _make_context()
    bot = _make_bot(support_telegram="onlytg", support_phone=None)

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = bot

    with patch.object(_mod, "SessionLocal", return_value=mock_db):
        _run(_mod.support_callback(update, context))

    text = update.callback_query.edit_message_text.call_args.args[0]
    assert "@onlytg" in text
    assert "تلفن" not in text  # no phone line


def test_support_callback_shows_no_info_message_when_no_contacts():
    update = _make_update(callback_data="support")
    context = _make_context()
    bot = _make_bot(support_telegram=None, support_phone=None)

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = bot

    with patch.object(_mod, "SessionLocal", return_value=mock_db):
        _run(_mod.support_callback(update, context))

    text = update.callback_query.edit_message_text.call_args.args[0]
    assert "ثبت نشده" in text


def test_support_callback_handles_bot_not_found():
    update = _make_update(callback_data="support")
    context = _make_context()

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = None

    with patch.object(_mod, "SessionLocal", return_value=mock_db):
        _run(_mod.support_callback(update, context))

    text = update.callback_query.edit_message_text.call_args.args[0]
    assert "ثبت نشده" in text


# ---------------------------------------------------------------------------
# register
# ---------------------------------------------------------------------------


def test_register_adds_three_handlers():
    app = MagicMock()
    _mod.register(app)
    assert app.add_handler.call_count == 3
