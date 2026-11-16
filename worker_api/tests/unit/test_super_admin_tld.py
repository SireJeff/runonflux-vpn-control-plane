"""Phase 2 boundary test: activating a subscription/dashboard TLD does NOT fire
a global end-user notice.

Pre-Phase-2 (single-active), every activation flipped everyone's domain and
fanned out a notice (``_broadcast_tld_change`` + ``_enqueue_end_user_tld_notice``).
Multi-active activation only ADDS a TLD to the pool — no existing user's
effective URL changes — so the global notice is suppressed on the activation
path. (Phase 3 will generalize notifications to affected-admins-only on the
deactivate/delete paths, where ``migrate_off`` genuinely moves URLs.)

These tests guard against accidentally re-adding the broadcast/notice to
activation. They drive the real async ``_activate_*_tld`` helpers with DNS mocked.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import app.api.v1.endpoints.super_admin as _mod

_TASK = "app.tasks.end_user_notifications.notify_end_users_tld_changed"


def _run(coro):
    return asyncio.run(coro)


def _make_tld(domain="sub.new.link", purpose="subscription"):
    return MagicMock(
        domain=domain,
        dns_provider="cloudflare",
        zone_id="z",
        server_ip="1.2.3.4",
        is_active=False,
        purpose=purpose,
    )


def test_activate_subscription_tld_does_not_enqueue_global_notice():
    """Multi-active: activating a subscription TLD must NOT fan out a global
    end-user notice or broadcast (no user's URL changed)."""
    new_tld = _make_tld(purpose="subscription")
    mock_db = MagicMock()

    with patch.object(_mod, "create_dns_client") as mk, patch(
        _TASK
    ) as mock_task, patch.object(
        _mod, "_broadcast_tld_change", new=AsyncMock(return_value=1)
    ) as mock_broadcast:
        mk.return_value = AsyncMock()
        _run(_mod._activate_subscription_tld(mock_db, new_tld, None))

    mock_task.delay.assert_not_called()
    mock_broadcast.assert_not_called()


def test_activate_dashboard_tld_does_not_enqueue_global_notice():
    """Multi-active: activating a dashboard TLD must NOT fan out a global notice."""
    new_tld = _make_tld(purpose="dashboard")
    mock_db = MagicMock()

    with patch.object(_mod, "create_dns_client") as mk, patch(
        _TASK
    ) as mock_task, patch.object(
        _mod, "_broadcast_tld_change", new=AsyncMock(return_value=1)
    ) as mock_broadcast:
        mk.return_value = AsyncMock()
        _run(_mod._activate_dashboard_tld(mock_db, new_tld, None))

    mock_task.delay.assert_not_called()
    mock_broadcast.assert_not_called()
