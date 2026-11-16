"""Unit tests for build_webhook_url -- the function that decides where
Telegram sends updates for reseller bots.

This is the regression test for the bug where build_webhook_url was using
get_dashboard_base_url (panel.operator5.example.invalid) instead of get_api_base_url
(api.operator7.example.invalid), causing all webhooks to hit the Next.js container and
return 404.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.bots.bot_lifecycle_service import (
    BotLifecycleError,
    build_webhook_url,
    get_webhook_info,
)


def _mock_db():
    return MagicMock()


def test_build_webhook_url_uses_api_domain_not_portal_domain():
    """CRITICAL: webhook URL must be on api.operator7.example.invalid, not panel.operator5.example.invalid.

    Regression: previously this returned https://panel.operator5.example.invalid/bot/X/webhook
    which routed to the Next.js container and silently dropped all updates.
    """
    with patch(
        "app.services.url_resolver.get_api_base_url",
        return_value="https://api.operator7.example.invalid",
    ):
        url = build_webhook_url(bot_id=42, db=_mock_db())
    assert (
        url == "https://api.operator7.example.invalid/bot/42/webhook"
    ), f"Expected api.operator7.example.invalid, got {url}"


def test_build_webhook_url_strips_trailing_slash_from_base():
    """If base URL has trailing /, the resulting URL must not have //."""
    with patch(
        "app.services.url_resolver.get_api_base_url",
        return_value="https://api.operator7.example.invalid/",
    ):
        url = build_webhook_url(bot_id=7, db=_mock_db())
    assert url == "https://api.operator7.example.invalid/bot/7/webhook"


def test_build_webhook_url_path_format():
    """Path must be exactly /bot/{bot_id}/webhook to match FastAPI route."""
    with patch(
        "app.services.url_resolver.get_api_base_url",
        return_value="https://api.operator7.example.invalid",
    ):
        url = build_webhook_url(bot_id=99, db=_mock_db())
    assert url.endswith("/bot/99/webhook")
    # Must NOT have /api/v1 prefix -- the webhook route is mounted at root.
    assert "/api/v1/bot/" not in url


def test_build_webhook_url_never_uses_portal_domain():
    """Belt-and-braces: under no circumstances should the portal domain appear."""
    with patch(
        "app.services.url_resolver.get_api_base_url",
        return_value="https://api.operator7.example.invalid",
    ):
        url = build_webhook_url(bot_id=1, db=_mock_db())
    assert (
        "panel.operator5.example.invalid" not in url
    ), f"Portal domain leaked into webhook URL: {url}"


@pytest.mark.asyncio
async def test_get_webhook_info_returns_result_on_success():
    """get_webhook_info should return Telegram's result dict on 200 + ok=true."""
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {
        "ok": True,
        "result": {
            "url": "https://api.operator7.example.invalid/bot/42/webhook",
            "has_custom_certificate": False,
            "pending_update_count": 0,
            "max_connections": 40,
            "ip_address": "1.2.3.4",
            "last_error_date": None,
            "last_error_message": None,
        },
    }

    mock_client = AsyncMock()
    mock_client.get.return_value = fake_response
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await get_webhook_info("fake:token")
    assert result["url"] == "https://api.operator7.example.invalid/bot/42/webhook"
    assert result["pending_update_count"] == 0


@pytest.mark.asyncio
async def test_get_webhook_info_raises_on_non_200():
    """Non-200 response should raise BotLifecycleError."""
    fake_response = MagicMock()
    fake_response.status_code = 401
    fake_response.text = "Unauthorized"

    mock_client = AsyncMock()
    mock_client.get.return_value = fake_response
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(BotLifecycleError):
            await get_webhook_info("bad:token")
