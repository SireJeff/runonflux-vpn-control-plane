"""Unit tests for end-user setup guides (Task 3 navigation)."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import app.services.bots.end_user_guides as _mod


def _run(coro):
    return asyncio.run(coro)


def _make_update(user_id=12345, callback_data="guide:android"):
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


def test_guide_has_back_and_home():
    """Guide screen keyboard includes Back (->my_sub) and Home (nav_footer)."""
    update = _make_update(callback_data="guide:android")
    context = _make_context()
    user = MagicMock()
    user.language = "fa"
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = user
    with patch.object(_mod, "SessionLocal", return_value=mock_db):
        _run(_mod.guide_android_callback(update, context))
    markup = update.callback_query.edit_message_text.call_args.kwargs["reply_markup"]
    cbs = [b.callback_data for row in markup.inline_keyboard for b in row]
    assert "my_sub" in cbs  # back
    assert "main_menu" in cbs  # home
