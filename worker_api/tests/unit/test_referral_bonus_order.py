import secrets
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.models.admin_free_config import AdminFreeConfig
from app.models.admin_referral import AdminReferralConfig, AdminReferralEarning
from app.models.admin_users import AdminUser
from app.models.admins import Admin
from app.models.free_config_enrollment import FreeConfigEnrollment
from app.models.free_config_global import FreeConfigGlobal
from app.models.user_credentials_v2 import UserCredentialV2
from app.models.user_orders import UserOrder
from app.services.free_config.policy import MIB
from app.services.orders.order_service import OrderService
from app.services.referral.bonus_service import ReferralBonusService


def _base(db, reward_type):
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
            is_enabled=True,
            default_daily_limit_mb=200,
            max_referral_bonus_mb=1000,
            verification_bot_token_enc=b"t",
        )
    )
    db.add(
        AdminFreeConfig(
            admin_id=a.id, is_enabled=True, kind="per_user", daily_limit_mb=200
        )
    )
    db.add(
        AdminReferralConfig(
            admin_id=a.id,
            is_enabled=True,
            reward_type=reward_type,
            reward_percentage=Decimal("10.00"),
            traffic_per_referral_mb=10,
            traffic_max_bonus_mb=500,
        )
    )
    db.commit()
    return a


def _user(db, admin_id, username, referred_by=None, enrolled=False):
    u = AdminUser(
        admin_id=admin_id,
        username=username,
        status="active",
        telegram_id=int(secrets.token_hex(4), 16),
        language="fa",
        subscription_token=secrets.token_hex(16),
        traffic_limit_bytes=200 * MIB,
        referred_by_user_id=referred_by,
        wallet_credit_tomans=Decimal("0"),
    )
    db.add(u)
    db.commit()
    if enrolled:
        db.add(
            FreeConfigEnrollment(user_id=u.id, admin_id=admin_id, membership_ok=True)
        )
        db.commit()
    return u


def test_cashback_suppressed_when_reward_type_traffic(db_session):
    a = _base(db_session, reward_type="traffic")
    ref = _user(db_session, a.id, "ref")
    buyer = _user(db_session, a.id, "buyer", referred_by=ref.id)
    order = UserOrder(
        admin_id=a.id,
        user_id=buyer.id,
        status="approved",
        amount_tomans=Decimal("100000"),
        wallet_credit_applied_tomans=Decimal("0"),
    )
    db_session.add(order)
    db_session.commit()

    OrderService(db_session)._maybe_award_referral(buyer, order)

    db_session.refresh(ref)
    assert ref.wallet_credit_tomans == Decimal("0")  # no cashback in traffic-only mode
    assert db_session.query(AdminReferralEarning).count() == 0


def test_cashback_awarded_when_reward_type_both(db_session):
    a = _base(db_session, reward_type="both")
    ref = _user(db_session, a.id, "ref")
    buyer = _user(db_session, a.id, "buyer", referred_by=ref.id)
    order = UserOrder(
        admin_id=a.id,
        user_id=buyer.id,
        status="approved",
        amount_tomans=Decimal("100000"),
        wallet_credit_applied_tomans=Decimal("0"),
    )
    db_session.add(order)
    db_session.commit()

    OrderService(db_session)._maybe_award_referral(buyer, order)

    db_session.refresh(ref)
    assert ref.wallet_credit_tomans == Decimal("10000.00")  # 10% of 100000


def test_paid_referee_keeps_counting_for_referrer(db_session):
    a = _base(db_session, reward_type="both")
    ref = _user(db_session, a.id, "ref", enrolled=True)  # free referrer, base 200
    friend = _user(db_session, a.id, "friend", referred_by=ref.id)
    friend.expires_at = datetime.utcnow() + timedelta(days=30)  # now a paid customer
    friend.status = "active"
    db_session.commit()

    ReferralBonusService(db_session).apply_effective_limit(ref)
    db_session.refresh(ref)
    assert ref.traffic_limit_bytes == (200 + 10) * MIB  # paid friend counts


def test_activate_subscription_recomputes_referrer_bonus(db_session, monkeypatch):
    # When a referred buyer's subscription is activated via _activate_subscription,
    # the referrer's traffic bonus should be recomputed (paid branch).
    import app.services.orders.order_service as mod

    monkeypatch.setattr(mod, "set_user_regions", lambda *a, **k: None)
    monkeypatch.setattr(
        "app.services.regions.availability.healthy_macro_codes", lambda db: ["eu"]
    )

    a = _base(db_session, reward_type="both")
    ref = _user(db_session, a.id, "ref", enrolled=True)  # free referrer, base 200 MB
    buyer = _user(db_session, a.id, "buyer", referred_by=ref.id)

    # Create a subscription order for the buyer
    order = UserOrder(
        admin_id=a.id,
        user_id=buyer.id,
        kind="subscription",
        package_snapshot={
            "name": "Basic",
            "traffic_gb": 50,
            "duration_days": 30,
            "price_tomans": 300000,
        },
        macro_region="eu",
        macro_regions=["eu"],
        amount_tomans=Decimal("300000"),
        status="pending",
    )
    db_session.add(order)
    db_session.commit()

    # Drive _activate_subscription end-to-end
    svc = OrderService(db_session)
    svc._activate_subscription(
        order, buyer, datetime.now(timezone.utc).replace(tzinfo=None)
    )

    # Refresh referrer and assert the bonus was recomputed
    db_session.refresh(ref)
    assert ref.traffic_limit_bytes == (200 + 10) * MIB  # paid buyer counts


def test_activate_subscription_recomputes_referrer_bonus_for_enrolled_buyer_with_creds(
    db_session, monkeypatch
):
    # Real-world free->paid conversion: the buyer was already an enrolled
    # free-config user AND already has credential rows (e.g. they claimed a
    # free config earlier). In that case _activate_subscription's
    # `existing_creds == 0` check is False, so CredentialService.
    # generate_user_credentials (which commits) is SKIPPED. Without a flush
    # right before the referrer recompute, the buyer's brand-new expires_at
    # is only pending (autoflush=False) and the enrollment row was already
    # deleted in this same call, so count_qualifying's raw aggregate matches
    # neither the free branch nor the paid branch for this referee, and the
    # referrer's bonus is wrongly recomputed as if the referee doesn't count.
    import app.services.orders.order_service as mod

    monkeypatch.setattr(mod, "set_user_regions", lambda *a, **k: None)
    monkeypatch.setattr(
        "app.services.regions.availability.healthy_macro_codes", lambda db: ["eu"]
    )

    a = _base(db_session, reward_type="both")
    ref = _user(db_session, a.id, "ref", enrolled=True)  # free referrer, base 200 MB
    buyer = _user(db_session, a.id, "buyer", referred_by=ref.id, enrolled=True)

    # Buyer already has a credential row (claimed the free config earlier),
    # so generate_user_credentials will be skipped on activation.
    db_session.add(
        UserCredentialV2(
            user_id=buyer.id,
            protocol="ssh",
            credential_data={"username": buyer.username, "password": "x"},
        )
    )
    db_session.commit()

    order = UserOrder(
        admin_id=a.id,
        user_id=buyer.id,
        kind="subscription",
        package_snapshot={
            "name": "Basic",
            "traffic_gb": 50,
            "duration_days": 30,
            "price_tomans": 300000,
        },
        macro_region="eu",
        macro_regions=["eu"],
        amount_tomans=Decimal("300000"),
        status="pending",
    )
    db_session.add(order)
    db_session.commit()

    svc = OrderService(db_session)
    svc._activate_subscription(
        order, buyer, datetime.now(timezone.utc).replace(tzinfo=None)
    )

    db_session.refresh(ref)
    assert ref.traffic_limit_bytes == (200 + 10) * MIB  # converted friend still counts
