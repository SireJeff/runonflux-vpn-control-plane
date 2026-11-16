"""Unit tests for receipt_storage.download_and_store.

Mocks httpx.AsyncClient so no network calls. Uses tmp_path for filesystem.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.orders import receipt_storage as _mod


def _run(coro):
    """Run an async coroutine from sync test code."""
    return asyncio.run(coro)


def _make_fake_client(get_file_resp=None, get_content_resp=None):
    """Build a mock httpx.AsyncClient with the two-step download pattern.

    __aenter__ must return self so ``async with ... as client`` yields
    the same object whose .get() side_effect is configured.
    """
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)

    # First call: getFile -> returns JSON with file_path
    file_resp = MagicMock()
    file_resp.raise_for_status = MagicMock()
    file_resp.json.return_value = get_file_resp or {
        "ok": True,
        "result": {"file_path": "photos/file_123.jpg"},
    }
    # Second call: download content
    content_resp = MagicMock()
    content_resp.raise_for_status = MagicMock()
    content_resp.content = get_content_resp or b"\xff\xd8fake-jpeg"

    client.get = AsyncMock(side_effect=[file_resp, content_resp])
    return client


def test_download_and_store_writes_file_and_returns_path(tmp_path, monkeypatch):
    """Happy path: file is written to RECEIPTS_DIR/{order_id}.jpg."""
    monkeypatch.setattr(_mod, "RECEIPTS_DIR", tmp_path)

    fake_client = _make_fake_client()
    with patch("httpx.AsyncClient", return_value=fake_client):
        result = _run(_mod.download_and_store("BOT_TOKEN", "file_abc", 42))

    expected = tmp_path / "42.jpg"
    assert str(expected) == result
    assert expected.read_bytes() == b"\xff\xd8fake-jpeg"


def test_download_and_store_raises_on_telegram_error(tmp_path, monkeypatch):
    """If Telegram returns ok=false, raise RuntimeError."""
    monkeypatch.setattr(_mod, "RECEIPTS_DIR", tmp_path)

    fake_client = _make_fake_client(
        get_file_resp={"ok": False, "description": "file_id not found"},
    )
    with patch("httpx.AsyncClient", return_value=fake_client):
        with pytest.raises(RuntimeError, match="getFile failed"):
            _run(_mod.download_and_store("BOT_TOKEN", "bad_file_id", 99))


def test_download_and_store_creates_dir_if_missing(tmp_path, monkeypatch):
    """RECEIPTS_DIR is created on first call."""
    nested = tmp_path / "nested" / "subdir"
    monkeypatch.setattr(_mod, "RECEIPTS_DIR", nested)

    fake_client = _make_fake_client()
    with patch("httpx.AsyncClient", return_value=fake_client):
        _run(_mod.download_and_store("BOT_TOKEN", "file_abc", 1))

    assert nested.exists()
    assert (nested / "1.jpg").exists()
