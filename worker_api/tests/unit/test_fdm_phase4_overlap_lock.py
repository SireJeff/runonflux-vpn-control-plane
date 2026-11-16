"""Phase 4.3 unit tests: the overlap_lock async context manager.

Tests the helper in isolation (no FdmSyncService dependency). get_redis is
patched on the overlap_lock module; the redis client is a MagicMock.
"""
import asyncio
import logging
from unittest.mock import MagicMock, patch

import pytest
import redis

from app.core import overlap_lock as ol


def _run(coro):
    return asyncio.run(coro)


# --- T1: acquire success -------------------------------------------------


def test_acquire_success_sets_nx_ex_with_uuid_token():
    fake = MagicMock()
    fake.set.return_value = True  # SET NX EX succeeded
    with patch.object(ol, "get_redis", return_value=fake):

        async def body():
            async with ol.overlap_lock("fdm:sync:lock") as acquired:
                return acquired

        acquired = _run(body())

    assert acquired is True
    fake.set.assert_called_once()
    args, kwargs = fake.set.call_args
    assert args[0] == "fdm:sync:lock"
    token = args[1]
    assert isinstance(token, str) and len(token) == 32  # uuid4().hex
    assert kwargs.get("nx") is True
    assert kwargs.get("ex") == ol.DEFAULT_TTL  # 1200


# --- T2: lock held -> yield False, no release ----------------------------


def test_lock_held_yields_false_and_skips_release():
    fake = MagicMock()
    fake.set.return_value = None  # NX failed -> already held
    with patch.object(ol, "get_redis", return_value=fake):

        async def body():
            async with ol.overlap_lock("fdm:sync:lock") as acquired:
                return acquired

        acquired = _run(body())

    assert acquired is False
    fake.eval.assert_not_called()  # didn't acquire -> nothing to release


# --- T3: Redis None -> fail-open ----------------------------------------


def test_none_redis_fail_open_logs_warning(caplog):
    with patch.object(ol, "get_redis", return_value=None):

        async def body():
            async with ol.overlap_lock("fdm:sync:lock") as acquired:
                return acquired

        with caplog.at_level(logging.WARNING, logger="app.core.overlap_lock"):
            acquired = _run(body())

    assert acquired is True
    assert any("Redis not configured" in r.message for r in caplog.records)


# --- T4: RedisError at acquire -> fail-open -----------------------------


def test_redis_error_at_acquire_fail_open(caplog):
    fake = MagicMock()
    fake.set.side_effect = redis.RedisError("boom")
    with patch.object(ol, "get_redis", return_value=fake):

        async def body():
            async with ol.overlap_lock("fdm:sync:lock") as acquired:
                return acquired

        with caplog.at_level(logging.WARNING, logger="app.core.overlap_lock"):
            acquired = _run(body())

    assert acquired is True
    assert any("acquire failed" in r.message for r in caplog.records)
    fake.eval.assert_not_called()


# --- T5: token-checked release (same token as acquire) ------------------


def test_release_uses_same_token_as_acquire():
    fake = MagicMock()
    fake.set.return_value = True
    fake.eval.return_value = 1
    with patch.object(ol, "get_redis", return_value=fake):

        async def body():
            async with ol.overlap_lock("fdm:sync:lock"):
                pass

        _run(body())

    set_token = fake.set.call_args.args[1]
    eval_args = fake.eval.call_args.args
    assert eval_args[0] == ol._RELEASE_SCRIPT  # the Lua script
    assert eval_args[1] == 1  # numkeys
    assert eval_args[2] == "fdm:sync:lock"  # KEYS[1]
    assert eval_args[3] == set_token  # ARGV[1] == acquire token


# --- T6: exception in body still releases + propagates ------------------


def test_exception_in_body_still_releases_and_propagates():
    fake = MagicMock()
    fake.set.return_value = True
    with patch.object(ol, "get_redis", return_value=fake):

        async def body():
            async with ol.overlap_lock("fdm:sync:lock"):
                raise RuntimeError("sync blew up")

        with pytest.raises(RuntimeError, match="sync blew up"):
            _run(body())

    fake.eval.assert_called_once()  # finally released despite the exception


# --- T7: TTL configurable (explicit param + settings read) --------------


def test_ttl_explicit_param_overrides_default():
    fake = MagicMock()
    fake.set.return_value = True
    with patch.object(ol, "get_redis", return_value=fake):

        async def body():
            async with ol.overlap_lock("fdm:sync:lock", ttl=99):
                pass

        _run(body())

    assert fake.set.call_args.kwargs["ex"] == 99


def test_ttl_reads_settings_when_no_param():
    fake = MagicMock()
    fake.set.return_value = True
    fake_settings = MagicMock()
    fake_settings.FDM_SYNC_LOCK_TTL_SECONDS = 555
    with patch.object(ol, "settings", fake_settings), patch.object(
        ol, "get_redis", return_value=fake
    ):

        async def body():
            async with ol.overlap_lock("fdm:sync:lock"):
                pass

        _run(body())

    assert fake.set.call_args.kwargs["ex"] == 555
