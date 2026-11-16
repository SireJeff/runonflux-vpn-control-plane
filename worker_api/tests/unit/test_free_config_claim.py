import asyncio
import secrets
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.models.admin_free_config import AdminFreeConfig
from app.models.admin_users import AdminUser
from app.models.admins import Admin
from app.models.free_config_channel import FreeConfigChannel
from app.models.free_config_enrollment import FreeConfigEnrollment
from app.models.free_config_global import FreeConfigGlobal
from app.services.free_config.membership_verifier import VerificationResult


def _setup(db, enabled=True, cap=None, channel=True):
    a = Admin(
        username="r" + secrets.token_hex(3),
        password_hash="x",
        status="active",
        default_macro_region="eu",
    )
    db.add(a)
    db.commit()
    db.add(
        FreeConfigGlobal(
            is_enabled=enabled,
            default_daily_limit_mb=200,
            verification_bot_token_enc=b"tok" if enabled else None,
        )
    )
    db.add(
        AdminFreeConfig(
            admin_id=a.id, is_enabled=enabled, kind="per_user", max_free_users=cap
        )
    )
    if channel:
        db.add(
            FreeConfigChannel(admin_id=None, chat_id=-100, title="G", is_active=True)
        )
    u = AdminUser(
        admin_id=a.id,
        username="u" + secrets.token_hex(3),
        status="lead",
        telegram_id=555,
        telegram_chat_id=555,
        language="fa",
        subscription_token=secrets.token_hex(16),
    )
    db.add(u)
    db.commit()
    return a, u


def _ctx(admin_id):
    app = SimpleNamespace(bot_data={"admin_id": admin_id})
    return SimpleNamespace(application=app)


def _update():
    q = SimpleNamespace(answer=AsyncMock(), edit_message_text=AsyncMock())
    return SimpleNamespace(callback_query=q, effective_user=SimpleNamespace(id=555))


def test_not_member_shows_join_screen_no_provision(db_session):
    a, u = _setup(db_session)
    from app.services.bots import end_user_free_config as mod

    upd = _update()
    with patch.object(mod, "SessionLocal", return_value=db_session), patch.object(
        mod,
        "_verify",
        new=AsyncMock(
            return_value=VerificationResult(
                ok=False,
                missing=[
                    SimpleNamespace(
                        username="@g", invite_url=None, chat_id=-100, title="G"
                    )
                ],
            )
        ),
    ):
        asyncio.run(mod.free_config_claim(upd, _ctx(a.id)))
    assert db_session.query(FreeConfigEnrollment).count() == 0
    upd.callback_query.edit_message_text.assert_awaited()


def test_member_provisions_and_returns_sub_link(db_session):
    a, u = _setup(db_session)
    from app.services.bots import end_user_free_config as mod

    upd = _update()
    with patch.object(mod, "SessionLocal", return_value=db_session), patch.object(
        mod, "_verify", new=AsyncMock(return_value=VerificationResult(ok=True))
    ):
        asyncio.run(mod.free_config_claim(upd, _ctx(a.id)))
    assert db_session.query(FreeConfigEnrollment).count() == 1
    text = upd.callback_query.edit_message_text.call_args.args[0]
    assert "/api/v1/user/sub/" in text


def test_unverifiable_fails_closed(db_session):
    a, u = _setup(db_session)
    from app.services.bots import end_user_free_config as mod

    upd = _update()
    with patch.object(mod, "SessionLocal", return_value=db_session), patch.object(
        mod,
        "_verify",
        new=AsyncMock(
            return_value=VerificationResult(
                ok=False, unverifiable=[SimpleNamespace(username="@g")]
            )
        ),
    ):
        asyncio.run(mod.free_config_claim(upd, _ctx(a.id)))
    assert db_session.query(FreeConfigEnrollment).count() == 0


def test_cap_full_shows_message_no_provision(db_session):
    a, u = _setup(db_session, cap=0)
    from app.services.bots import end_user_free_config as mod

    upd = _update()
    with patch.object(mod, "SessionLocal", return_value=db_session), patch.object(
        mod, "_verify", new=AsyncMock(return_value=VerificationResult(ok=True))
    ):
        asyncio.run(mod.free_config_claim(upd, _ctx(a.id)))
    assert db_session.query(FreeConfigEnrollment).count() == 0


def test_cap_rejection_releases_transaction_before_telegram_reply(db_session):
    a, _ = _setup(db_session, cap=0)
    from app.services.bots import end_user_free_config as mod

    upd = _update()

    async def reply(*args, **kwargs):
        assert not db_session.in_transaction()

    upd.callback_query.edit_message_text.side_effect = reply
    with patch.object(mod, "SessionLocal", return_value=db_session), patch.object(
        mod, "_verify", new=AsyncMock(return_value=VerificationResult(ok=True))
    ):
        asyncio.run(mod.free_config_claim(upd, _ctx(a.id)))


def test_paid_user_claim_returns_notice_without_link_or_changes(db_session):
    from datetime import datetime, timedelta

    a, u = _setup(db_session)
    u.status = "active"
    u.expires_at = datetime.utcnow() + timedelta(days=30)
    u.traffic_limit_bytes = 50 * 1024**3
    u.traffic_used_bytes = 123
    db_session.commit()
    from app.services.bots import end_user_free_config as mod

    upd = _update()
    with patch.object(mod, "SessionLocal", return_value=db_session), patch.object(
        mod, "_verify", new=AsyncMock(return_value=VerificationResult(ok=True))
    ):
        asyncio.run(mod.free_config_claim(upd, _ctx(a.id)))
    text = upd.callback_query.edit_message_text.call_args.args[0]
    assert "/api/v1/user/sub/" not in text
    assert db_session.query(FreeConfigEnrollment).count() == 0


def test_dispatcher_claim_creates_active_region_and_credentials_before_link(db_session):
    from app.models.user_credentials_v2 import UserCredentialV2
    from app.models.user_regions import UserRegion
    from app.services.bots import end_user_free_config as mod

    a, u = _setup(db_session, channel=False)
    user_id = u.id
    upd = _update()
    with patch.object(mod, "SessionLocal", return_value=db_session), patch.object(
        mod, "_verify", new=AsyncMock(return_value=VerificationResult(ok=True))
    ):
        asyncio.run(mod.free_config_callback(upd, _ctx(a.id)))
    saved = db_session.get(AdminUser, user_id)
    assert saved.status == "active" and saved.expires_at is None
    assert (
        db_session.query(UserRegion)
        .filter_by(user_id=user_id, status="active", macro_region="eu")
        .count()
        == 1
    )
    assert db_session.query(UserCredentialV2).filter_by(user_id=user_id).count() == 6
    assert (
        saved.subscription_token
        in upd.callback_query.edit_message_text.call_args.args[0]
    )
