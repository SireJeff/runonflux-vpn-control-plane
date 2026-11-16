"""FluxHealthMonitor must support the async context-manager protocol.

The celery flux tasks (worker_api/app/tasks/flux_tasks.py) all use
`async with FluxHealthMonitor() as monitor:`. The class defines close() but
historically lacked __aenter__/__aexit__, so every flux health-check /
metrics / restart task raised a TypeError ("does not support the
asynchronous context manager protocol"). These tests lock in the protocol.
"""

import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

# The flux service package pulls optional heavy SDKs transitively; stub the
# ones not installed in the unit env (mirrors sibling unit tests).
sys.modules.setdefault("cloudflare", MagicMock())

from app.services.flux.health_monitor import FluxHealthMonitor  # noqa: E402


def test_health_monitor_defines_async_context_protocol():
    assert hasattr(FluxHealthMonitor, "__aenter__")
    assert hasattr(FluxHealthMonitor, "__aexit__")


@pytest.mark.asyncio
async def test_async_with_yields_self_and_closes_client():
    fake_client = AsyncMock()  # stands in for FluxHybridClient; awaitable close()
    monitor = FluxHealthMonitor(flux_client=fake_client)

    async with monitor as m:
        assert m is monitor  # __aenter__ returns the monitor itself

    fake_client.close.assert_awaited_once()  # __aexit__ routed through close()


@pytest.mark.asyncio
async def test_async_exit_closes_client_even_on_exception():
    fake_client = AsyncMock()
    monitor = FluxHealthMonitor(flux_client=fake_client)

    with pytest.raises(ValueError):
        async with monitor:
            raise ValueError("boom")

    fake_client.close.assert_awaited_once()  # cleanup still runs on error
