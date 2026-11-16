import re
from unittest.mock import MagicMock, patch

import pytest

NOW = __import__("datetime").datetime(2026, 7, 27, 12, 0, 0)


def _svc():
    from app.services.subscriptions.adjustment_service import AdjustmentService

    db = MagicMock()
    added = []
    db.add.side_effect = lambda r: added.append(r)
    return AdjustmentService(db), db, added


def _no_collision(db):
    # db.query(AdminUser).filter(...).first() -> None  (name free globally)
    db.query.return_value.filter.return_value.first.return_value = None


def test_set_username_rejects_global_collision():
    svc, db, _ = _svc()
    db.query.return_value.filter.return_value.first.return_value = MagicMock(id=999)
    user = MagicMock(id=1, username="old_u")
    with pytest.raises(ValueError) as e:
        svc.set_username(user, admin_id=2, new_username="taken_u")
    assert "taken" in str(e.value)


def test_set_username_rejects_bad_charset():
    svc, db, _ = _svc()
    _no_collision(db)
    user = MagicMock(id=1, username="old_u")
    with pytest.raises(ValueError):
        svc.set_username(user, admin_id=2, new_username="bad name!")


def test_set_username_success_updates_reprovisions_and_audits():
    svc, db, added = _svc()
    _no_collision(db)
    user = MagicMock(id=1, username="old_u")
    with patch("app.services.subscriptions.adjustment_service.CredentialService") as CS:
        CS.return_value.reprovision_username.return_value = [
            "ssh",
            "http_proxy",
            "trojan",
        ]
        adj = svc.set_username(user, admin_id=2, new_username="new_u", reason="req")
    assert user.username == "new_u"
    CS.return_value.reprovision_username.assert_called_once_with(user)
    assert adj.action == "set_username"
    assert adj.details["from"] == "old_u" and adj.details["to"] == "new_u"
    assert adj.details["reprovisioned"] == ["ssh", "http_proxy", "trojan"]


def test_set_telegram_sets_and_audits():
    svc, db, added = _svc()
    db.query.return_value.filter.return_value.first.return_value = None  # no clash
    user = MagicMock(id=1, admin_id=2, telegram_id=None, telegram_chat_id=None)
    adj = svc.set_telegram(
        user, admin_id=2, telegram_id=555, telegram_chat_id=777, reason=None
    )
    assert user.telegram_id == 555 and user.telegram_chat_id == 777
    assert adj.action == "set_telegram"
    assert adj.details["to"]["telegram_id"] == 555


def test_set_telegram_clear_detaches():
    svc, db, added = _svc()
    user = MagicMock(id=1, admin_id=2, telegram_id=555, telegram_chat_id=777)
    adj = svc.set_telegram(
        user, admin_id=2, telegram_id=None, telegram_chat_id=None, reason=None
    )
    assert user.telegram_id is None and user.telegram_chat_id is None
    assert adj.details["to"]["telegram_id"] is None


def test_set_telegram_rejects_same_reseller_collision():
    svc, db, added = _svc()
    db.query.return_value.filter.return_value.first.return_value = MagicMock(id=99)
    user = MagicMock(id=1, admin_id=2, telegram_id=None, telegram_chat_id=None)
    with pytest.raises(ValueError):
        svc.set_telegram(
            user, admin_id=2, telegram_id=555, telegram_chat_id=None, reason=None
        )


def test_reset_used_traffic_zeros_and_audits():
    svc, db, added = _svc()
    user = MagicMock(
        id=1,
        traffic_used_bytes=9 * 1024**3,
        traffic_limit_bytes=5 * 1024**3,
        status="active",
    )
    adj = svc.reset_used_traffic(user, admin_id=2, reason=None)
    assert user.traffic_used_bytes == 0
    assert user.traffic_limit_bytes == 5 * 1024**3  # limit untouched
    assert user.status == "active"  # status untouched
    assert adj.action == "reset_traffic"


def test_set_traffic_limit_absolute_and_unlimited():
    svc, db, added = _svc()
    user = MagicMock(id=1, traffic_limit_bytes=1 * 1024**3)
    adj = svc.set_traffic_limit(user, admin_id=2, gb=50, reason=None)
    assert user.traffic_limit_bytes == 50 * 1024**3
    assert adj.action == "set_traffic_limit"
    adj2 = svc.set_traffic_limit(user, admin_id=2, gb=None, reason=None)
    assert user.traffic_limit_bytes is None  # unlimited
    assert adj2.details["to_bytes"] is None


def test_set_status_suspend_and_activate():
    svc, db, added = _svc()
    user = MagicMock(id=1, status="active")
    a1 = svc.set_status(user, admin_id=2, active=False, reason=None)
    assert user.status == "suspended" and a1.action == "suspend"
    a2 = svc.set_status(user, admin_id=2, active=True, reason=None)
    assert user.status == "active" and a2.action == "activate"


def test_record_password_reset_never_stores_secret():
    svc, db, added = _svc()
    user = MagicMock(id=1)
    adj = svc.record_password_reset(user, admin_id=2, reason=None)
    assert adj.action == "reset_password"
    assert adj.details == {"changed": True}
