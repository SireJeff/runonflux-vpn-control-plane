"""Unit tests for the read-only order-history screen."""

import asyncio
from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import app.services.bots.end_user_orders as _mod


def _run(coro):
    return asyncio.run(coro)


def _make_update(user_id=12345):
    u = MagicMock()
    u.effective_user.id = user_id
    u.callback_query = MagicMock()
    u.callback_query.answer = AsyncMock()
    u.callback_query.edit_message_text = AsyncMock()
    u.callback_query.data = "orders"
    return u


def _make_context(admin_id=5):
    c = MagicMock()
    c.application.bot_data = {"admin_id": admin_id}
    return c


def _make_order(i, status="pending"):
    o = MagicMock()
    o.id = 100 + i
    o.package_snapshot = {"name": f"Plan {i}"}
    o.macro_region = "eu"
    o.amount_tomans = Decimal("250000")
    o.status = status
    o.created_at = datetime(2026, 8, 1)
    return o


def _db_with(user, orders):
    db = MagicMock()
    # first query -> user; second query chain -> orders
    db.query.return_value.filter.return_value.first.return_value = user
    (
        db.query.return_value.filter.return_value.order_by.return_value.all.return_value
    ) = orders
    return db


def test_orders_empty_state_shows_buy():
    update, context = _make_update(), _make_context()
    user = MagicMock(id=50, language="en")
    db = _db_with(user, [])
    with patch.object(_mod, "SessionLocal", return_value=db):
        _run(_mod.orders_callback(update, context))
    text = update.callback_query.edit_message_text.call_args.args[0]
    assert "no orders" in text.lower()
    kb = update.callback_query.edit_message_text.call_args.kwargs["reply_markup"]
    flat = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert "buy" in flat


def test_orders_list_newest_first_lines_and_pager():
    update, context = _make_update(), _make_context()
    user = MagicMock(id=50, language="en")
    orders = [_make_order(i) for i in range(8)]  # 2 pages of 6
    db = _db_with(user, orders)
    with patch.object(_mod, "SessionLocal", return_value=db):
        _run(_mod.orders_callback(update, context))
    text = update.callback_query.edit_message_text.call_args.args[0]
    assert "#100" in text and "Plan 0" in text and "Pending" in text
    kb = update.callback_query.edit_message_text.call_args.kwargs["reply_markup"]
    flat = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert "pgorders:1" in flat  # 2 pages -> pager present
    assert "my_sub" in flat  # back_to my_sub in nav_footer
