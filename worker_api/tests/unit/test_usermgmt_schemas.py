import pytest
from pydantic import ValidationError


def test_set_username_request_enforces_charset():
    from app.schemas.user_adjustments import SetUsernameRequest

    assert SetUsernameRequest(new_username="good_name1").new_username == "good_name1"
    with pytest.raises(ValidationError):
        SetUsernameRequest(new_username="bad name!")
    with pytest.raises(ValidationError):
        SetUsernameRequest(new_username="ab")  # too short


def test_set_telegram_request_allows_null_clear():
    from app.schemas.user_adjustments import SetTelegramRequest

    r = SetTelegramRequest(telegram_id=None, telegram_chat_id=None)
    assert r.telegram_id is None and r.telegram_chat_id is None
    r2 = SetTelegramRequest(telegram_id=123, telegram_chat_id=456)
    assert r2.telegram_id == 123


def test_renew_request_has_absolute_limit_fields():
    from app.schemas.user_adjustments import RenewUserRequest

    r = RenewUserRequest(set_traffic_limit_gb=50)
    assert float(r.set_traffic_limit_gb) == 50.0
    r2 = RenewUserRequest(set_unlimited=True)
    assert r2.set_unlimited is True


def test_reset_traffic_request_optional_reason():
    from app.schemas.user_adjustments import ResetTrafficRequest

    assert ResetTrafficRequest().reason is None
    assert ResetTrafficRequest(reason="cleanup").reason == "cleanup"


def test_user_detail_response_exposes_telegram():
    from app.schemas.admin_api import UserDetailResponse

    d = UserDetailResponse(
        id=1, username="u", status="active", telegram_id=42, telegram_chat_id=43
    )
    assert d.telegram_id == 42 and d.telegram_chat_id == 43
