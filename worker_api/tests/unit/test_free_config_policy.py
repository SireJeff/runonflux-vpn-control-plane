import pytest
from app.services.free_config.policy import resolve_free_config_policy, EffectivePolicy, MIB
from app.models.free_config_global import FreeConfigGlobal
from app.models.free_config_channel import FreeConfigChannel
from app.models.admin_free_config import AdminFreeConfig
from app.models.admins import Admin


def _mk_admin(db):
    a = Admin(username="r1", password_hash="x", status="active", default_macro_region="eu")
    db.add(a); db.commit()
    return a


def test_disabled_when_global_off(db_session):
    a = _mk_admin(db_session)
    db_session.add(FreeConfigGlobal(is_enabled=False, default_daily_limit_mb=200))
    db_session.add(AdminFreeConfig(admin_id=a.id, is_enabled=True, kind="per_user"))
    db_session.commit()
    p = resolve_free_config_policy(db_session, a.id)
    assert p.enabled is False


def test_disabled_when_token_missing(db_session):
    a = _mk_admin(db_session)
    db_session.add(FreeConfigGlobal(is_enabled=True, default_daily_limit_mb=200, verification_bot_token_enc=None))
    db_session.add(AdminFreeConfig(admin_id=a.id, is_enabled=True, kind="per_user"))
    db_session.commit()
    p = resolve_free_config_policy(db_session, a.id)
    assert p.enabled is False


def test_enabled_and_limit_clamped_to_ceiling(db_session):
    a = _mk_admin(db_session)
    db_session.add(FreeConfigGlobal(is_enabled=True, default_daily_limit_mb=200, verification_bot_token_enc=b"tok"))
    db_session.add(AdminFreeConfig(admin_id=a.id, is_enabled=True, kind="per_user", daily_limit_mb=5000))
    db_session.commit()
    p = resolve_free_config_policy(db_session, a.id)
    assert p.enabled is True
    assert p.daily_limit_mb == 200                 # reseller 5000 clamped to ceiling 200
    assert p.daily_limit_bytes == 200 * MIB


def test_limit_inherits_global_default_when_reseller_null(db_session):
    a = _mk_admin(db_session)
    db_session.add(FreeConfigGlobal(is_enabled=True, default_daily_limit_mb=150, verification_bot_token_enc=b"tok"))
    db_session.add(AdminFreeConfig(admin_id=a.id, is_enabled=True, kind="per_user", daily_limit_mb=None))
    db_session.commit()
    p = resolve_free_config_policy(db_session, a.id)
    assert p.daily_limit_mb == 150


def test_channels_are_union_and_deduped(db_session):
    a = _mk_admin(db_session)
    db_session.add(FreeConfigGlobal(is_enabled=True, default_daily_limit_mb=200, verification_bot_token_enc=b"tok"))
    db_session.add(AdminFreeConfig(admin_id=a.id, is_enabled=True, kind="per_user"))
    db_session.add(FreeConfigChannel(admin_id=None, username="@global", title="G", is_active=True))
    db_session.add(FreeConfigChannel(admin_id=a.id, username="@reseller", title="R", is_active=True))
    db_session.add(FreeConfigChannel(admin_id=a.id, username="@global", title="dupe", is_active=True))  # dupe of global
    db_session.add(FreeConfigChannel(admin_id=a.id, username="@inactive", title="X", is_active=False))
    db_session.commit()
    p = resolve_free_config_policy(db_session, a.id)
    handles = sorted(c.username for c in p.required_channels)
    assert handles == ["@global", "@reseller"]     # deduped, inactive excluded


def test_reseller_zero_limit_is_honored(db_session):
    a = _mk_admin(db_session)
    db_session.add(FreeConfigGlobal(is_enabled=True, default_daily_limit_mb=200, verification_bot_token_enc=b"tok"))
    db_session.add(AdminFreeConfig(admin_id=a.id, is_enabled=True, kind="per_user", daily_limit_mb=0))
    db_session.commit()
    p = resolve_free_config_policy(db_session, a.id)
    assert p.daily_limit_mb == 0                    # 0 is lower than ceiling 200 -> honored
    assert p.daily_limit_bytes == 0


def test_channels_deduped_by_chat_id(db_session):
    a = _mk_admin(db_session)
    db_session.add(FreeConfigGlobal(is_enabled=True, default_daily_limit_mb=200, verification_bot_token_enc=b"tok"))
    db_session.add(AdminFreeConfig(admin_id=a.id, is_enabled=True, kind="per_user"))
    db_session.add(FreeConfigChannel(admin_id=None, chat_id=-100, username="@global", title="G", is_active=True))
    db_session.add(FreeConfigChannel(admin_id=a.id, chat_id=-100, username="@reseller", title="R", is_active=True))
    db_session.commit()
    p = resolve_free_config_policy(db_session, a.id)
    assert len(p.required_channels) == 1            # same chat_id deduped to one


def test_region_falls_back_to_admin_default(db_session):
    a = _mk_admin(db_session)
    db_session.add(FreeConfigGlobal(is_enabled=True, default_daily_limit_mb=200, verification_bot_token_enc=b"tok"))
    db_session.add(AdminFreeConfig(admin_id=a.id, is_enabled=True, kind="per_user", region=None))
    db_session.commit()
    p = resolve_free_config_policy(db_session, a.id)
    assert p.region == "eu"
