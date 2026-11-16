"""Tests for ResellerBotManager lazy Application init."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.bots.reseller_bot_manager import BotInactiveError, ResellerBotManager


@pytest.mark.asyncio
async def test_get_or_create_app_lazy_init():
    """First call inits Application; second call returns cached instance."""
    manager_db = MagicMock()

    fake_app = AsyncMock()
    fake_app.bot_data = {}

    manager = ResellerBotManager(
        manager_db,
        app_builder=lambda token: fake_app,
        handler_registrar=None,
    )

    # Stub _load_bot_config so we don't hit the DB
    bot_mock = MagicMock(
        id=1,
        admin_id=10,
        is_active=True,
        bot_token_enc=b"\x00" * 28,
    )
    manager._load_bot_config = lambda bot_id: bot_mock

    # Stub token_loader so we don't decrypt
    manager._token_loader = lambda bot: "DECRYPTED"

    app1 = await manager.get_or_create_app(bot_id=1)
    app2 = await manager.get_or_create_app(bot_id=1)

    assert app1 is app2
    assert app1.bot_data["bot_id"] == 1
    assert app1.bot_data["admin_id"] == 10
    fake_app.initialize.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_or_create_app_raises_on_inactive_bot():
    manager = ResellerBotManager(MagicMock())
    manager._load_bot_config = lambda bot_id: MagicMock(is_active=False)
    with pytest.raises(BotInactiveError):
        await manager.get_or_create_app(bot_id=1)


@pytest.mark.asyncio
async def test_get_or_create_app_raises_on_missing_bot():
    manager = ResellerBotManager(MagicMock())
    manager._load_bot_config = lambda bot_id: None
    with pytest.raises(BotInactiveError):
        await manager.get_or_create_app(bot_id=1)


@pytest.mark.asyncio
async def test_evict_removes_cached_app():
    manager = ResellerBotManager(MagicMock())
    fake_app = AsyncMock()
    fake_app.bot_data = {}
    fake_app.shutdown = AsyncMock()
    manager._apps[1] = fake_app

    await manager.evict(bot_id=1)
    assert 1 not in manager._apps
    fake_app.shutdown.assert_awaited()


def test_load_bot_config_uses_fresh_session_and_closes_it():
    """_load_bot_config opens a session from the factory and closes it.

    The manager must NOT reuse one long-lived session for per-webhook lookups
    (that pins a pooled connection for the process lifetime and shares session
    state across concurrent async webhooks). Each lookup gets its own short
    session that is always closed.
    """
    fake_session = MagicMock()
    bot_row = MagicMock(id=1, admin_id=10, is_active=True, bot_token_enc=b"x")
    fake_session.query.return_value.filter.return_value.first.return_value = bot_row

    calls = []

    def factory():
        calls.append(1)
        return fake_session

    manager = ResellerBotManager(MagicMock(), session_factory=factory)
    snap = manager._load_bot_config(1)

    assert snap is not None
    assert snap.id == 1
    assert snap.admin_id == 10
    assert snap.is_active is True
    assert snap.bot_token_enc == b"x"
    assert len(calls) == 1
    fake_session.close.assert_called_once()


def test_load_bot_config_does_not_use_shared_db():
    """The db passed to the constructor is NOT used for per-lookup queries."""
    shared = MagicMock()
    fake_session = MagicMock()
    fake_session.query.return_value.filter.return_value.first.return_value = None

    manager = ResellerBotManager(shared, session_factory=lambda: fake_session)
    manager._load_bot_config(99)

    shared.query.assert_not_called()
    fake_session.close.assert_called_once()


def test_load_bot_config_closes_session_on_query_error():
    """A query failure still closes the short-lived session (no leak)."""
    fake_session = MagicMock()
    fake_session.query.side_effect = RuntimeError("boom")

    manager = ResellerBotManager(MagicMock(), session_factory=lambda: fake_session)
    with pytest.raises(RuntimeError):
        manager._load_bot_config(1)

    fake_session.close.assert_called_once()


@pytest.mark.asyncio
async def test_handler_registrar_is_called_on_init():
    """If handler_registrar is provided, it's called with the new Application."""
    manager_db = MagicMock()
    fake_app = AsyncMock()
    fake_app.bot_data = {}

    registrar_calls = []

    def registrar(app):
        registrar_calls.append(app)

    manager = ResellerBotManager(
        manager_db,
        app_builder=lambda token: fake_app,
        handler_registrar=registrar,
    )
    manager._load_bot_config = lambda bot_id: MagicMock(
        id=1,
        admin_id=10,
        is_active=True,
        bot_token_enc=b"\x00" * 28,
    )
    manager._token_loader = lambda bot: "DECRYPTED"

    await manager.get_or_create_app(bot_id=1)
    assert registrar_calls == [fake_app]
