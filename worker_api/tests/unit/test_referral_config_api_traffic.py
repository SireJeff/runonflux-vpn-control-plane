import secrets

from app.api.v1.endpoints.referral_api import update_config
from app.models.admins import Admin
from app.models.free_config_global import FreeConfigGlobal
from app.schemas.referral import ReferralConfigUpdate


def _admin(db, ceiling=300):
    a = Admin(username="r" + secrets.token_hex(3), password_hash="x", status="active")
    db.add(a)
    db.commit()
    db.add(
        FreeConfigGlobal(
            is_enabled=True, default_daily_limit_mb=200, max_referral_bonus_mb=ceiling
        )
    )
    db.commit()
    return a


def test_update_sets_traffic_fields(db_session):
    a = _admin(db_session, ceiling=1000)
    req = ReferralConfigUpdate(
        reward_type="both", traffic_per_referral_mb=10, traffic_max_bonus_mb=500
    )
    cfg = update_config(req, current={"id": a.id, "entity": a}, db=db_session)
    assert cfg.reward_type == "both"
    assert cfg.traffic_per_referral_mb == 10
    assert cfg.traffic_max_bonus_mb == 500


def test_update_clamps_max_bonus_to_global_ceiling(db_session):
    a = _admin(db_session, ceiling=300)
    req = ReferralConfigUpdate(traffic_max_bonus_mb=500)
    cfg = update_config(req, current={"id": a.id, "entity": a}, db=db_session)
    assert cfg.traffic_max_bonus_mb == 300  # clamped down


def test_update_rejects_bad_reward_type(db_session):
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ReferralConfigUpdate(reward_type="gold")
