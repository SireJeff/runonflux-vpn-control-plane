"""Regression guard for the 2026-08-16 FDM freeze incident.

Both FDM DNS provider clients (ArvanCloud, Cloudflare) MUST bound their
per-request timeout. Without a bound, a blackholed/slow provider stalls each
call (aiohttp default 300s; Cloudflare SDK 60s x auto-retries), and because the
sync calls them serially per-domain, a full pool blows the Celery 3600s hard
limit -> SIGKILL -> the whole FDM sync never completes and every region's
health/IP data freezes. These tests fail if the timeout bound is removed.
"""
import aiohttp
import pytest

from app.services.fdm.arvancloud_client import ArvanCloudDnsClient
from app.services.fdm.cloudflare_client import CloudflareDnsClient


def test_arvancloud_request_timeout_is_bounded():
    t = ArvanCloudDnsClient._REQUEST_TIMEOUT
    assert isinstance(t, aiohttp.ClientTimeout)
    # A single DNS call must fail fast, well under the 3600s task limit.
    assert t.total is not None and t.total <= 30
    assert t.sock_connect is not None and t.sock_connect <= 10


@pytest.mark.asyncio
async def test_arvancloud_session_uses_bounded_timeout():
    client = ArvanCloudDnsClient(api_key="k", domain="example.com")
    try:
        session = await client._get_session()
        assert session.timeout.total is not None and session.timeout.total <= 30
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_cloudflare_client_bounds_timeout_and_retries():
    from unittest.mock import patch

    client = CloudflareDnsClient(api_token="t", zone_id="z", domain="example.com")
    with patch("app.services.fdm.cloudflare_client.AsyncCloudflare") as MockCF:
        await client._get_client()
    _, kwargs = MockCF.call_args
    assert kwargs.get("timeout") is not None and kwargs["timeout"] <= 30
    assert kwargs.get("max_retries") is not None and kwargs["max_retries"] <= 1
