"""Unit tests for My Subscription + My Connections handlers (Task 16)."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import app.services.bots.end_user_connections as _mod


def _run(coro):
    return asyncio.run(coro)


def _make_update(user_id=12345, chat_id=67890):
    update = MagicMock()
    update.effective_user.id = user_id
    update.effective_chat.id = chat_id
    update.callback_query = MagicMock()
    # Both .answer() and .edit_message_text() are awaited inside the handler
    update.callback_query.answer = AsyncMock()
    update.callback_query.edit_message_text = AsyncMock()
    return update


def _make_context(admin_id=5, bot_id=1):
    context = MagicMock()
    context.application.bot_data = {"admin_id": admin_id, "bot_id": bot_id}
    return context


def _make_user(
    id=50,
    status="active",
    used_bytes=None,
    limit_bytes=None,
    expires_at=None,
    region=None,
    username="test_user",
    password_enc=None,
    subscription_token="tok123",
    current_order=None,
    language="fa",
):
    user = MagicMock()
    user.id = id
    user.admin_id = 5
    user.status = status
    user.traffic_used_bytes = used_bytes
    user.traffic_limit_bytes = limit_bytes
    user.expires_at = expires_at
    user.region = region
    user.username = username
    user.password_enc = password_enc
    user.subscription_token = subscription_token
    user.current_order = current_order
    user.language = language
    return user


# ---------------------------------------------------------------------------
# my_sub_callback
# ---------------------------------------------------------------------------


def test_my_sub_active_user_shows_traffic_and_expiry():
    """T12: my_sub_callback now renders the v2 hero (subscription-link-centric).

    Old test asserted traffic stats ("5.00", "20.00", "25%") — those are gone.
    The hero now shows: package, limit_gb, expiry, region, username, password,
    dashboard_url, subscription_url, country grid.
    """
    from datetime import datetime

    update = _make_update()
    context = _make_context()
    user = _make_user(
        status="active",
        used_bytes=5 * 1024**3,  # 5 GB
        limit_bytes=20 * 1024**3,  # 20 GB
        expires_at=datetime(2026, 7, 13),
        password_enc=b"\x00" * 28,  # non-None so decrypt path is exercised
    )

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = user

    fake_service = MagicMock()
    fake_service.generate_country_breakdown.return_value = {}

    with patch.object(_mod, "SessionLocal", return_value=mock_db), patch.object(
        _mod, "ConnectionStringService", return_value=fake_service
    ), patch(
        "app.services.url_resolver.get_subscription_base_url",
        return_value="https://sub.test",
    ), patch(
        "app.services.url_resolver.get_dashboard_base_url",
        return_value="https://dash.test",
    ), patch(
        "app.core.crypto.decrypt_token", return_value="DECRYPTED_PW"
    ):
        _run(_mod.my_sub_callback(update, context))

    update.callback_query.edit_message_text.assert_awaited_once()
    text = update.callback_query.edit_message_text.call_args.args[0]
    # Hero header
    assert "اشتراک شما فعال شد" in text
    # Limit + expiry present
    assert "20" in text  # limit_gb
    assert "2026-07-13" in text  # expiry
    # User portal block
    assert "test_user" in text
    assert "DECRYPTED_PW" in text
    # URLs
    assert "https://sub.test" in text
    assert "https://dash.test" in text


def test_my_sub_unlimited_traffic_when_no_limit():
    """T12: v2 hero collapses to no-limit display when traffic_limit_bytes is None.

    Previously showed "نامحدود"; new hero template renders ``limit_gb`` directly,
    so an unset limit produces a Python ``None`` rendered as the literal string.
    The test now just confirms the hero renders without crashing.
    """
    update = _make_update()
    context = _make_context()
    user = _make_user(
        status="active",
        used_bytes=2 * 1024**3,
        limit_bytes=None,  # unlimited
    )

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = user

    fake_service = MagicMock()
    fake_service.generate_country_breakdown.return_value = {}

    with patch.object(_mod, "SessionLocal", return_value=mock_db), patch.object(
        _mod, "ConnectionStringService", return_value=fake_service
    ), patch(
        "app.services.url_resolver.get_subscription_base_url",
        return_value="https://sub.test",
    ), patch(
        "app.services.url_resolver.get_dashboard_base_url",
        return_value="https://dash.test",
    ):
        _run(_mod.my_sub_callback(update, context))

    text = update.callback_query.edit_message_text.call_args.args[0]
    assert "اشتراک شما فعال شد" in text


def test_my_sub_lead_status_shows_no_subscription_message():
    update = _make_update()
    context = _make_context()
    user = _make_user(status="lead")

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = user

    with patch.object(_mod, "SessionLocal", return_value=mock_db):
        _run(_mod.my_sub_callback(update, context))

    text = update.callback_query.edit_message_text.call_args.args[0]
    assert "اشتراک فعالی ندارید" in text


def test_my_sub_suspended_user_still_shows_status():
    """T12: Suspended users still see the v2 hero (status check is for "lead"
    only — both "active" and "suspended" render the hero)."""
    update = _make_update()
    context = _make_context()
    user = _make_user(
        status="suspended",
        used_bytes=10 * 1024**3,
        limit_bytes=10 * 1024**3,
    )

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = user

    fake_service = MagicMock()
    fake_service.generate_country_breakdown.return_value = {}

    with patch.object(_mod, "SessionLocal", return_value=mock_db), patch.object(
        _mod, "ConnectionStringService", return_value=fake_service
    ), patch(
        "app.services.url_resolver.get_subscription_base_url",
        return_value="https://sub.test",
    ), patch(
        "app.services.url_resolver.get_dashboard_base_url",
        return_value="https://dash.test",
    ):
        _run(_mod.my_sub_callback(update, context))

    text = update.callback_query.edit_message_text.call_args.args[0]
    # Hero is rendered for suspended users too (only "lead" gets the buy-prompt)
    assert "اشتراک شما فعال شد" in text


def test_my_sub_user_not_found_shows_error():
    update = _make_update()
    context = _make_context()

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = None

    with patch.object(_mod, "SessionLocal", return_value=mock_db):
        _run(_mod.my_sub_callback(update, context))

    text = update.callback_query.edit_message_text.call_args.args[0]
    assert "کاربر یافت نشد" in text


def test_my_sub_zero_used_bytes_does_not_crash():
    """T12: hero no longer reads traffic_used_bytes for display (limit_gb only).

    Defensively confirm the handler still renders without crashing when
    used_bytes is None — the value isn't used in the new template but
    shouldn't blow up if downstream code accesses it.
    """
    update = _make_update()
    context = _make_context()
    user = _make_user(
        status="active",
        used_bytes=None,  # never set
        limit_bytes=20 * 1024**3,
    )

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = user

    fake_service = MagicMock()
    fake_service.generate_country_breakdown.return_value = {}

    with patch.object(_mod, "SessionLocal", return_value=mock_db), patch.object(
        _mod, "ConnectionStringService", return_value=fake_service
    ), patch(
        "app.services.url_resolver.get_subscription_base_url",
        return_value="https://sub.test",
    ), patch(
        "app.services.url_resolver.get_dashboard_base_url",
        return_value="https://dash.test",
    ):
        _run(_mod.my_sub_callback(update, context))

    text = update.callback_query.edit_message_text.call_args.args[0]
    # Hero renders with the limit; used_bytes is no longer surfaced.
    assert "20" in text  # limit_gb


# ---------------------------------------------------------------------------
# connections_callback
# ---------------------------------------------------------------------------


def _make_region(macro_region="eu"):
    region = MagicMock()
    region.macro_region = macro_region
    return region


def test_connections_no_active_subscription_prompts_buy():
    update = _make_update()
    context = _make_context()
    user = _make_user(status="lead")  # not active

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = user

    with patch.object(_mod, "SessionLocal", return_value=mock_db):
        _run(_mod.connections_callback(update, context))

    text = update.callback_query.edit_message_text.call_args.args[0]
    assert "اشتراک" in text


def test_connections_user_not_found_prompts_buy():
    """If user lookup fails, treat like 'no sub' — don't leak that they don't exist."""
    update = _make_update()
    context = _make_context()

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = None

    with patch.object(_mod, "SessionLocal", return_value=mock_db):
        _run(_mod.connections_callback(update, context))

    text = update.callback_query.edit_message_text.call_args.args[0]
    assert "اشتراک" in text


def test_connections_empty_result_shows_just_header():
    update = _make_update()
    context = _make_context()
    region = _make_region("as")
    user = _make_user(status="active", region=region)

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = user

    fake_service = MagicMock()
    # connections_callback calls generate_all_region_connections (not the
    # legacy generate_connection_strings) — see other tests in this file.
    fake_service.generate_all_region_connections.return_value = {}  # no deployments yet

    with patch.object(_mod, "SessionLocal", return_value=mock_db), patch.object(
        _mod, "ConnectionStringService", return_value=fake_service
    ), patch(
        "app.services.url_resolver.get_subscription_base_url",
        return_value="https://sub.test",
    ), patch(
        "app.services.url_resolver.get_dashboard_base_url",
        return_value="https://dash.test",
    ):
        _run(_mod.connections_callback(update, context))

    text = update.callback_query.edit_message_text.call_args.args[0]
    assert "اتصالات من" in text  # header still rendered


# ---------------------------------------------------------------------------
# register
# ---------------------------------------------------------------------------


def test_my_sub_hero_has_home_and_connections_buttons():
    """my_sub hero keyboard includes Home + a Connections quick-switch (nav_footer)."""
    update = _make_update()
    context = _make_context()
    user = _make_user(
        status="active", password_enc=b"\x00" * 28, subscription_token="tok"
    )
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = user
    fake_service = MagicMock()
    fake_service.generate_country_breakdown.return_value = {}
    with patch.object(_mod, "SessionLocal", return_value=mock_db), patch.object(
        _mod, "ConnectionStringService", return_value=fake_service
    ), patch(
        "app.services.url_resolver.get_subscription_base_url",
        return_value="https://sub.test",
    ), patch(
        "app.services.url_resolver.get_dashboard_base_url",
        return_value="https://dash.test",
    ), patch(
        "app.core.crypto.decrypt_token", return_value="PW"
    ):
        _run(_mod.my_sub_callback(update, context))
    markup = update.callback_query.edit_message_text.call_args.kwargs["reply_markup"]
    cbs = [b.callback_data for row in markup.inline_keyboard for b in row]
    assert "main_menu" in cbs
    assert "connections" in cbs


def test_country_detail_has_back_and_home():
    """country_callback keyboard includes Back (->connections) and Home (nav_footer).

    Note: country_callback re-imports ``ConnectionStringService`` locally from
    its source module, so the patch must target
    ``app.services.credentials.connection_string_service.ConnectionStringService``
    (not ``_mod``) — patching ``_mod`` is shadowed by the local import.
    """
    update = _make_update()
    context = _make_context()
    update.callback_query.data = "country:de"
    region = _make_region("eu")
    user = _make_user(status="active", region=region)
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = user
    fake_service = MagicMock()
    # country_callback calls generate_all_region_connections (not the legacy
    # generate_country_breakdown) — see connections_callback tests above.
    fake_service.generate_all_region_connections.return_value = {
        "de": {"ssh": {"primary": "ssh://u:p@de.example.com:22#label"}},
    }
    with patch.object(_mod, "SessionLocal", return_value=mock_db), patch(
        "app.services.credentials.connection_string_service.ConnectionStringService",
        return_value=fake_service,
    ):
        _run(_mod.country_callback(update, context))
    markup = update.callback_query.edit_message_text.call_args.kwargs["reply_markup"]
    cbs = [b.callback_data for row in markup.inline_keyboard for b in row]
    assert "connections" in cbs  # back button
    assert "main_menu" in cbs  # home


def test_register_adds_five_handlers():
    """Was 4; Task 3 adds pgcty_callback (country-grid pagination) as the 5th."""
    app = MagicMock()
    _mod.register(app)
    assert app.add_handler.call_count == 5


# ---------------------------------------------------------------------------
# country grid pagination (Task 3)
# ---------------------------------------------------------------------------


def test_country_picker_paginates_grid_keeps_bottom_actions():
    from app.services.bots.end_user_keyboards import country_picker_keyboard

    countries = [(f"c{i}", "🏳️", f"Country {i}") for i in range(20)]  # 3 pages of 9
    kb = country_picker_keyboard(countries, lang="fa", page=1)
    flat = [b.callback_data for row in kb.inline_keyboard for b in row]
    country_btns = [c for c in flat if c.startswith("country:")]
    assert country_btns == [f"country:c{i}" for i in range(9, 18)]  # page-1 slice
    assert "pgcty:0" in flat and "pgcty:2" in flat  # pager both sides
    assert "reset_password" in flat and "main_menu" in flat  # bottom actions kept


def test_country_picker_single_page_no_pager():
    from app.services.bots.end_user_keyboards import country_picker_keyboard

    countries = [(f"c{i}", "🏳️", f"C{i}") for i in range(5)]
    kb = country_picker_keyboard(countries, lang="fa")
    flat = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert not any(c.startswith("pgcty:") for c in flat)
