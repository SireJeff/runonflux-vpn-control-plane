"""ArvanCloud rate-limit budget (Phase 4.4).

Fixed-window Redis counter shared across all FDM processes. Fail-open if
Redis is unavailable. A real 429 from ArvanCloud immediately caps the
current window (self-corrects a too-generous configured default).

Pure unit tests — no DB, no network (aiohttp + redis are mocked).
"""
import asyncio

import pytest
import redis as redis_module

from app.services.fdm import arvancloud_client as ac
from app.services.fdm.arvancloud_client import (
    ArvanCloudDnsClient,
    ArvanCloudDnsClientError,
    ArvanCloudRateLimitBudgetExceeded,
)


def _client():
    return ArvanCloudDnsClient(api_key="test-key", domain="operator1.example.invalid")


class _FakeRedis:
    """Minimal sync-Redis stand-in. `count` is what `incr` returns each call
    (simulates the window's running total); `raise_on` names methods that
    should raise redis.RedisError instead of executing."""

    def __init__(self, count=1, raise_on=None):
        self.count = count
        self.raise_on = raise_on or set()
        self.calls = []

    def incr(self, key):
        self.calls.append(("incr", key))
        if "incr" in self.raise_on:
            raise redis_module.RedisError("boom")
        return self.count

    def expire(self, key, seconds):
        self.calls.append(("expire", key, seconds))
        if "expire" in self.raise_on:
            raise redis_module.RedisError("boom")

    def set(self, key, value, ex=None):
        self.calls.append(("set", key, value, ex))
        if "set" in self.raise_on:
            raise redis_module.RedisError("boom")


def test_budget_exceeded_is_subclass_of_arvancloud_error():
    assert issubclass(ArvanCloudRateLimitBudgetExceeded, ArvanCloudDnsClientError)


def test_check_budget_allows_call_when_under_limit(monkeypatch):
    fake = _FakeRedis(count=1)  # 1st call this window, MAX_CALLS default is 30
    monkeypatch.setattr(ac, "get_redis", lambda: fake)
    client = _client()

    asyncio.run(client._check_budget())  # must not raise

    assert ("incr",) == fake.calls[0][:1]


def test_check_budget_sets_ttl_on_first_call_in_window(monkeypatch):
    fake = _FakeRedis(count=1)
    monkeypatch.setattr(ac, "get_redis", lambda: fake)
    client = _client()

    asyncio.run(client._check_budget())

    assert "expire" in [c[0] for c in fake.calls]


def test_check_budget_does_not_set_ttl_when_not_first_call(monkeypatch):
    fake = _FakeRedis(count=5)  # not the first call in this window
    monkeypatch.setattr(ac, "get_redis", lambda: fake)
    client = _client()

    asyncio.run(client._check_budget())

    assert "expire" not in [c[0] for c in fake.calls]


def test_check_budget_raises_when_over_limit(monkeypatch):
    client = _client()
    max_calls, _ = client._rate_limit_config()
    fake = _FakeRedis(count=max_calls + 1)  # over the configured MAX_CALLS
    monkeypatch.setattr(ac, "get_redis", lambda: fake)

    with pytest.raises(ArvanCloudRateLimitBudgetExceeded):
        asyncio.run(client._check_budget())


def test_check_budget_allows_call_at_exactly_the_limit(monkeypatch):
    client = _client()
    max_calls, _ = client._rate_limit_config()
    fake = _FakeRedis(count=max_calls)  # exactly at the limit -- allowed, next raises
    monkeypatch.setattr(ac, "get_redis", lambda: fake)

    asyncio.run(client._check_budget())  # must not raise


def test_check_budget_fail_open_when_redis_none(monkeypatch):
    monkeypatch.setattr(ac, "get_redis", lambda: None)
    client = _client()

    asyncio.run(client._check_budget())  # must not raise


def test_check_budget_fail_open_when_redis_error(monkeypatch):
    fake = _FakeRedis(count=1, raise_on={"incr"})
    monkeypatch.setattr(ac, "get_redis", lambda: fake)
    client = _client()

    asyncio.run(client._check_budget())  # must not raise -- fail open


def test_handle_error_429_caps_current_window(monkeypatch):
    fake = _FakeRedis(count=1)
    monkeypatch.setattr(ac, "get_redis", lambda: fake)
    client = _client()

    class _Resp:
        status = 429

        async def text(self):
            return "rate limited"

    with pytest.raises(ArvanCloudDnsClientError):
        asyncio.run(client._handle_error(_Resp(), "test op"))

    max_calls, _ = client._rate_limit_config()
    set_calls = [c for c in fake.calls if c[0] == "set"]
    assert len(set_calls) == 1
    assert set_calls[0][2] == max_calls  # capped to the configured MAX_CALLS


def test_handle_error_non_429_does_not_cap_window(monkeypatch):
    fake = _FakeRedis(count=1)
    monkeypatch.setattr(ac, "get_redis", lambda: fake)
    client = _client()

    class _Resp:
        status = 500

        async def text(self):
            return "server error"

    with pytest.raises(ArvanCloudDnsClientError):
        asyncio.run(client._handle_error(_Resp(), "test op"))

    assert "set" not in [c[0] for c in fake.calls]


def test_ensure_record_exists_reraises_budget_exceeded_without_reconcile_fallback(
    monkeypatch,
):
    """A budget-exceeded update must propagate immediately -- NOT be treated
    like a generic update failure that falls through to reconcile-by-name
    (which would just burn a second local budget check for nothing useful)."""
    from unittest.mock import AsyncMock

    client = _client()
    client.update_dns_record = AsyncMock(
        side_effect=ArvanCloudRateLimitBudgetExceeded("budget exhausted")
    )
    client.find_a_record_by_name = AsyncMock(return_value=None)
    client.create_dns_record = AsyncMock(return_value={"id": "should-not-happen"})

    with pytest.raises(ArvanCloudRateLimitBudgetExceeded):
        asyncio.run(
            client.ensure_record_exists(
                name="x", ip="1.2.3.4", existing_record_id="rec-1"
            )
        )

    client.find_a_record_by_name.assert_not_awaited()
    client.create_dns_record.assert_not_awaited()
