from unittest.mock import MagicMock, patch

from app.services.notifications.router import NotificationRouter, SendResult


def _resp(status_code, json_body=None):
    m = MagicMock()
    m.status_code = status_code
    m.json.return_value = json_body or {}
    return m


def _patch_post(resp):
    client = MagicMock()
    client.__enter__.return_value.post.return_value = resp
    return patch("app.services.notifications.router.httpx.Client", return_value=client)


def test_200_is_sent():
    with _patch_post(_resp(200, {"ok": True})):
        r = NotificationRouter.send_raw("t", 1, "hi")
    assert r == SendResult("sent")


def test_403_is_blocked():
    body = {"ok": False, "error_code": 403, "description": "Forbidden: bot was blocked by the user"}
    with _patch_post(_resp(403, body)):
        r = NotificationRouter.send_raw("t", 1, "hi")
    assert r.status == "blocked"


def test_429_is_failed_with_retry_after():
    body = {"ok": False, "error_code": 429, "parameters": {"retry_after": 7}}
    with _patch_post(_resp(429, body)):
        r = NotificationRouter.send_raw("t", 1, "hi")
    assert r.status == "failed"
    assert r.retry_after == 7.0


def test_500_is_failed():
    with _patch_post(_resp(500, {"ok": False})):
        r = NotificationRouter.send_raw("t", 1, "hi")
    assert r.status == "failed"


def test_exception_is_failed():
    client = MagicMock()
    client.__enter__.return_value.post.side_effect = RuntimeError("boom")
    with patch("app.services.notifications.router.httpx.Client", return_value=client):
        r = NotificationRouter.send_raw("t", 1, "hi")
    assert r.status == "failed"


def test_button_reply_markup_passed_through():
    captured = {}

    def _post(url, json):
        captured["json"] = json
        return _resp(200, {"ok": True})

    client = MagicMock()
    client.__enter__.return_value.post.side_effect = _post
    markup = {"inline_keyboard": [[{"text": "Open", "url": "https://x.io"}]]}
    with patch("app.services.notifications.router.httpx.Client", return_value=client):
        NotificationRouter.send_raw("t", 1, "hi", reply_markup=markup)
    assert captured["json"]["reply_markup"] == markup
    assert captured["json"]["parse_mode"] == "HTML"
