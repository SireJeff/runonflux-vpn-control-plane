"""Tests for send_telegram_alert chunking behavior.

The chunking helper has subtle edge cases (hard-split long lines, empty messages,
multi-byte safe, etc.) worth pinning down.
"""

from app.services.notifications.send_alert import (
    TELEGRAM_TEXT_LIMIT,
    _chunk_message,
    send_telegram_alert,
)


class TestChunkMessage:
    def test_short_message_returns_single_chunk(self):
        msg = "hello world"
        assert _chunk_message(msg) == [msg]

    def test_exactly_at_limit_returns_single_chunk(self):
        msg = "a" * TELEGRAM_TEXT_LIMIT
        chunks = _chunk_message(msg)
        assert len(chunks) == 1
        assert len(chunks[0]) == TELEGRAM_TEXT_LIMIT

    def test_just_over_limit_splits_into_two(self):
        msg = "a" * (TELEGRAM_TEXT_LIMIT + 1)
        chunks = _chunk_message(msg)
        assert len(chunks) == 2
        assert len(chunks[0]) == TELEGRAM_TEXT_LIMIT
        assert len(chunks[1]) == 1

    def test_splits_at_line_boundaries_when_possible(self):
        # Two halves each under limit, joined by newline
        half = "x" * 200
        msg = half + "\n" + half
        chunks = _chunk_message(msg, max_len=201)
        assert len(chunks) == 2
        assert chunks[0] == half
        assert chunks[1] == half

    def test_hard_splits_lines_longer_than_max(self):
        # Single line that's 2x the limit must be hard-split
        msg = "y" * (TELEGRAM_TEXT_LIMIT * 2)
        chunks = _chunk_message(msg)
        assert len(chunks) == 2
        assert all(len(c) == TELEGRAM_TEXT_LIMIT for c in chunks)

    def test_hard_splits_with_existing_buffer_flush(self):
        # A short line followed by a huge line: short line should flush first
        short = "first\n"
        huge = "z" * (TELEGRAM_TEXT_LIMIT + 100)
        msg = short + huge
        chunks = _chunk_message(msg)
        assert len(chunks) == 3
        assert chunks[0] == "first"
        assert chunks[1] == "z" * TELEGRAM_TEXT_LIMIT
        assert chunks[2] == "z" * 100

    def test_empty_message_returns_single_empty_chunk(self):
        assert _chunk_message("") == [""]

    def test_multiline_under_limit_preserved(self):
        msg = "\n".join(["line1", "line2", "line3"])
        assert _chunk_message(msg) == [msg]


class TestSendTelegramAlertChunking:
    def test_returns_false_when_no_token(self, monkeypatch):
        from app.services.notifications import send_alert

        monkeypatch.setattr(send_alert.settings, "TELEGRAM_BOT_TOKEN", None)
        assert send_telegram_alert(123, "hi") is False

    def test_returns_false_when_no_chat_id(self, monkeypatch):
        from app.services.notifications import send_alert

        monkeypatch.setattr(send_alert.settings, "TELEGRAM_BOT_TOKEN", "tok")
        assert send_telegram_alert(0, "hi") is False

    def test_long_message_sends_multiple_chunks(self, monkeypatch):
        """Verify chunking: a 6000-char message results in 2 POSTs."""
        from app.services.notifications import send_alert

        monkeypatch.setattr(send_alert.settings, "TELEGRAM_BOT_TOKEN", "fake-token")

        calls: list[str] = []

        class FakeResp:
            def raise_for_status(self):
                pass

        class FakeClient:
            def __init__(self, *args, **kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def post(self, url, json):
                calls.append(json["text"])
                return FakeResp()

        monkeypatch.setattr(send_alert.httpx, "Client", FakeClient)

        msg = "x" * 6000  # over 4096
        result = send_telegram_alert(42, msg)

        assert result is True
        assert len(calls) == 2
        assert all(len(c) <= TELEGRAM_TEXT_LIMIT for c in calls)
        assert "".join(calls) == msg

    def test_failure_in_second_chunk_returns_false(self, monkeypatch):
        """If chunk 2 fails, the whole call is a failure."""
        from app.services.notifications import send_alert

        monkeypatch.setattr(send_alert.settings, "TELEGRAM_BOT_TOKEN", "fake-token")

        post_count = [0]

        class FakeResp:
            def __init__(self, fail):
                self.fail = fail

            def raise_for_status(self):
                if self.fail:
                    raise Exception("simulated 400")

        class FakeClient:
            def __init__(self, *args, **kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def post(self, url, json):
                post_count[0] += 1
                return FakeResp(fail=(post_count[0] == 2))

        monkeypatch.setattr(send_alert.httpx, "Client", FakeClient)

        msg = "x" * 6000
        assert send_telegram_alert(42, msg) is False
