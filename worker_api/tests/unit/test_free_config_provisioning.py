"""Regression coverage for incomplete free users and unusable shared links."""

import base64
import secrets
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.api.v1.endpoints.end_user import get_subscription
from app.api.v1.endpoints.internal_v2 import sync_users
from app.models.admin_free_config import AdminFreeConfig
from app.models.admin_users import AdminUser
from app.models.admins import Admin
from app.models.free_config_enrollment import FreeConfigEnrollment
from app.models.free_config_global import FreeConfigGlobal
from app.models.user_credentials_v2 import UserCredentialV2
from app.models.user_regions import UserRegion
from app.services.credentials.connection_string_service import ConnectionStringService
from app.services.credentials.reseller_credential_service import CredentialService
from app.services.free_config.enrollment_service import FreeConfigEnrollmentService
from app.services.free_config.free_config_service import FreeConfigService
from app.services.free_config.policy import EffectivePolicy
from app.services.subscriptions.adjustment_service import AdjustmentService
from app.tasks.free_config_tasks import reset_daily_quotas_impl


def account(db):
    admin = Admin(
        username="reseller_" + secrets.token_hex(4),
        password_hash="test",
        status="active",
        wallet_balance=Decimal("100"),
        default_macro_region="eu",
    )
    db.add(admin)
    db.flush()
    user = AdminUser(
        admin_id=admin.id,
        username="customer_" + secrets.token_hex(4),
        status="lead",
        subscription_token=secrets.token_hex(16),
    )
    db.add(user)
    db.commit()
    return admin, user


def policy(region="eu"):
    return EffectivePolicy(True, [], 1024, 1073741824, 100, region)


def credentials(db, user):
    return {
        row.protocol: dict(row.credential_data)
        for row in db.query(UserCredentialV2).filter_by(user_id=user.id).all()
    }


def test_manual_activation_provisions_once_and_preserves_entitlement(db_session):
    admin, user = account(db_session)
    user.traffic_limit_bytes = 1073741824
    user.traffic_used_bytes = 123
    expiry = datetime.utcnow() + timedelta(days=4)
    user.expires_at = expiry
    db_session.commit()
    svc = AdjustmentService(db_session)
    svc.set_status(user, admin.id, active=True)
    db_session.commit()
    first = credentials(db_session, user)
    assert set(first) == {"ssh", "ss", "vless", "trojan", "outline", "http_proxy"}
    svc.set_status(user, admin.id, active=False)
    svc.set_status(user, admin.id, active=True)
    db_session.commit()
    assert credentials(db_session, user) == first
    assert (user.traffic_limit_bytes, user.traffic_used_bytes, user.expires_at) == (
        1073741824,
        123,
        expiry,
    )


def test_activation_rollback_does_not_commit_credentials_or_status(db_session):
    admin, user = account(db_session)
    user_id = user.id
    with Session(
        bind=db_session.connection(), join_transaction_mode="create_savepoint"
    ) as isolated:
        target = isolated.get(AdminUser, user_id)
        AdjustmentService(isolated).set_status(target, admin.id, active=True)
        assert len(credentials(isolated, target)) == 6
        isolated.rollback()
    db_session.expire_all()
    saved = db_session.get(AdminUser, user_id)
    assert saved.status == "lead"
    assert credentials(db_session, saved) == {}


@pytest.mark.parametrize("region", [None, "", "zz"])
def test_free_claim_rejects_missing_or_invalid_region_before_mutation(
    db_session, region
):
    _, user = account(db_session)
    with pytest.raises(ValueError):
        FreeConfigEnrollmentService(db_session).provision(user, policy(region))
    db_session.refresh(user)
    assert user.status == "lead"
    assert not credentials(db_session, user)
    assert db_session.query(FreeConfigEnrollment).count() == 0


@pytest.mark.parametrize("status", ["active", "suspended"])
def test_new_free_claim_cannot_overwrite_manual_or_paid_account(db_session, status):
    _, user = account(db_session)
    user.status = status
    user.traffic_limit_bytes = 50 * 1024**3
    user.traffic_used_bytes = 777
    user.expires_at = datetime.utcnow() + timedelta(days=20)
    db_session.commit()
    before = (
        user.status,
        user.traffic_limit_bytes,
        user.traffic_used_bytes,
        user.expires_at,
    )
    with pytest.raises(ValueError):
        FreeConfigEnrollmentService(db_session).provision(user, policy())
    db_session.refresh(user)
    assert (
        user.status,
        user.traffic_limit_bytes,
        user.traffic_used_bytes,
        user.expires_at,
    ) == before
    assert db_session.query(FreeConfigEnrollment).count() == 0


def test_reclaim_repairs_incomplete_enrollment_without_refilling_quota(db_session):
    admin, user = account(db_session)
    user.status = "active"
    user.traffic_limit_bytes = 1073741824
    user.traffic_used_bytes = 321
    token = user.subscription_token
    db_session.add(
        FreeConfigEnrollment(user_id=user.id, admin_id=admin.id, membership_ok=True)
    )
    db_session.commit()
    svc = FreeConfigEnrollmentService(db_session)
    svc.provision(user, policy())
    first = credentials(db_session, user)
    assert len(first) == 6
    assert (
        db_session.query(UserRegion)
        .filter_by(user_id=user.id, status="active", macro_region="eu")
        .count()
        == 1
    )
    svc.provision(user, policy())
    assert credentials(db_session, user) == first
    assert user.traffic_used_bytes == 321
    assert user.subscription_token == token


def test_manually_suspended_enrollment_is_not_claimable(db_session):
    _, user = account(db_session)
    svc = FreeConfigEnrollmentService(db_session)
    svc.provision(user, policy())
    user.status = "suspended"
    db_session.commit()
    with pytest.raises(ValueError):
        svc.provision(user, policy())
    assert user.status == "suspended"


def test_claim_refreshes_entitlement_changed_since_user_was_loaded(db_session):
    _, user = account(db_session)
    db_session.query(AdminUser).filter_by(id=user.id).update(
        {"status": "active", "traffic_limit_bytes": 53687091200},
        synchronize_session=False,
    )
    assert user.status == "lead"
    with pytest.raises(ValueError):
        FreeConfigEnrollmentService(db_session).provision(user, policy())
    db_session.refresh(user)
    assert user.status == "active" and user.traffic_limit_bytes == 53687091200


def test_manual_suspension_replaces_membership_ownership(db_session):
    admin, user = account(db_session)
    svc = FreeConfigEnrollmentService(db_session)
    enr = svc.provision(user, policy())
    user.status = "suspended"
    enr.suspended_reason = "membership"
    enr.membership_ok = False
    db_session.commit()
    AdjustmentService(db_session).set_status(user, admin.id, active=False)
    db_session.commit()
    with pytest.raises(ValueError):
        svc.provision(user, policy())
    assert user.status == "suspended"
    assert enr.suspended_reason == "manual"


def test_shared_rotation_uses_reseller_region_default(db_session):
    admin, _ = account(db_session)
    config = AdminFreeConfig(admin_id=admin.id, is_enabled=True, kind="shared")
    db_session.add(config)
    db_session.commit()
    FreeConfigService(db_session).rotate(admin.id)
    shared = db_session.query(AdminUser).filter_by(username=f"__free__{admin.id}").one()
    assert (
        db_session.query(UserRegion)
        .filter_by(user_id=shared.id, macro_region="eu", status="active")
        .count()
        == 1
    )


def test_enrollment_and_credentials_rollback_together_on_failure(db_session):
    _, user = account(db_session)
    user_id = user.id

    def fail_enrollment(*args):
        raise RuntimeError("failed enrollment insert")

    event.listen(FreeConfigEnrollment, "before_insert", fail_enrollment)
    try:
        with Session(
            bind=db_session.connection(), join_transaction_mode="create_savepoint"
        ) as isolated:
            target = isolated.get(AdminUser, user_id)
            with pytest.raises(RuntimeError, match="failed enrollment insert"):
                FreeConfigEnrollmentService(isolated).provision(target, policy())
            isolated.rollback()
    finally:
        event.remove(FreeConfigEnrollment, "before_insert", fail_enrollment)
    db_session.expire_all()
    saved = db_session.get(AdminUser, user_id)
    assert saved.status == "lead"
    assert credentials(db_session, saved) == {}
    assert db_session.query(UserRegion).filter_by(user_id=user_id).count() == 0
    assert db_session.query(FreeConfigEnrollment).count() == 0


@pytest.mark.parametrize(
    "fault",
    [
        "exhausted",
        "zero_limit",
        "expired",
        "inactive",
        "token_mismatch",
        "no_region",
        "no_credentials",
        "missing_user",
    ],
)
def test_shared_bundle_does_not_advertise_unusable_account(db_session, fault):
    admin, user = account(db_session)
    user.username = f"__free__{admin.id}"
    user.status = "active"
    user.traffic_limit_bytes = 1073741824
    db_session.add(
        UserRegion(user_id=user.id, macro_region="eu", status="active", is_primary=True)
    )
    config = AdminFreeConfig(
        admin_id=admin.id,
        is_enabled=True,
        kind="shared",
        region="eu",
        shared_credential_ref=user.subscription_token,
    )
    db_session.add(config)
    CredentialService(db_session).generate_user_credentials(user)
    if fault == "exhausted":
        user.traffic_used_bytes = 1073741824
    elif fault == "zero_limit":
        user.traffic_limit_bytes = 0
    elif fault == "expired":
        user.expires_at = datetime.utcnow() - timedelta(seconds=1)
    elif fault == "inactive":
        user.status = "suspended"
    elif fault == "token_mismatch":
        config.shared_credential_ref = "outdated"
    elif fault == "no_region":
        db_session.query(UserRegion).filter_by(user_id=user.id).delete()
    elif fault == "no_credentials":
        db_session.query(UserCredentialV2).filter_by(user_id=user.id).delete()
    elif fault == "missing_user":
        user.username = "not_the_shared_account"
    db_session.commit()
    assert FreeConfigService(db_session).public_bundle(admin.id) is None


def test_daily_free_account_subscription_sync_exhaustion_and_reset(db_session):
    admin, user = account(db_session)
    db_session.add(
        FreeConfigGlobal(
            is_enabled=True,
            default_daily_limit_mb=2000,
            verification_bot_token_enc=b"test",
        )
    )
    db_session.add(
        AdminFreeConfig(
            admin_id=admin.id,
            is_enabled=True,
            kind="per_user",
            region="eu",
            daily_limit_mb=1024,
        )
    )
    db_session.commit()
    svc = FreeConfigEnrollmentService(db_session)
    svc.provision(user, policy())
    first = credentials(db_session, user)
    assert len(first) == 6
    assert user.status == "active" and user.expires_at is None
    with patch.object(
        ConnectionStringService, "_resolve_fdm_effective", return_value=None
    ), patch.object(
        ConnectionStringService,
        "_get_domains_for_country",
        return_value=[("vpn.example.test", 443, None)],
    ):
        response = get_subscription(user.subscription_token, "base64", db_session)
    lines = base64.b64decode(response.body).decode().splitlines()
    assert any(
        line.startswith("vless://") and "vpn.example.test" in line for line in lines
    )
    assert user.username in {
        r.username for r in sync_users("vless", db_session, True).users
    }
    user.traffic_used_bytes = 1073741824
    db_session.commit()
    svc.provision(user, policy())
    assert user.traffic_used_bytes == 1073741824
    assert user.username not in {
        r.username for r in sync_users("vless", db_session, True).users
    }
    result = reset_daily_quotas_impl(db_session)
    assert result["errors"] == 0 and result["processed"] == 1
    assert user.traffic_used_bytes == 0 and user.traffic_limit_bytes == 1073741824
    assert user.username in {
        r.username for r in sync_users("vless", db_session, True).users
    }
    assert credentials(db_session, user) == first
