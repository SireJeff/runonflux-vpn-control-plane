from decimal import Decimal

import pytest

from app.models.admin_bots import AdminBot
from app.models.admin_packages import AdminPackage
from app.models.admin_users import AdminUser
from app.models.admins import Admin
from app.models.platform_settings import PlatformSetting
from app.models.user_orders import UserOrder
from app.services.orders.order_service import OrderError, OrderService

pytestmark = pytest.mark.database


def _seed(db, crypto_address="0xreseller-address"):
    """Seed a reseller (admin_id=1), an active package, and a pending user.

    ``crypto_address``: if not None, also seeds an AdminBot row for the
    reseller with that crypto_address (the reseller's crypto payment guard
    reads this via AdminBot.admin_id == user.admin_id). Pass None to leave
    the reseller without any AdminBot row at all (no bot configured).
    """
    db.add(
        Admin(
            id=1,
            username="r1",
            password_hash="x",
            status="active",
            wallet_balance=Decimal("0.00"),
        )
    )
    db.add(PlatformSetting(key="toman_per_usd_rate", value="60000"))
    db.flush()
    if crypto_address is not None:
        db.add(
            AdminBot(
                admin_id=1,
                bot_token_enc=b"\x00" * 28,
                bot_username="r1_bot",
                bot_user_id=1,
                webhook_secret="whsecret",
                crypto_address=crypto_address,
            )
        )
    pkg = AdminPackage(
        id=1,
        admin_id=1,
        name="Basic",
        traffic_limit_gb=Decimal("50"),
        duration_days=30,
        price_tomans=Decimal("3000000"),
        is_active=True,
    )
    user = AdminUser(
        id=1, admin_id=1, username="u1", password_hash="x", status="pending"
    )
    db.add(pkg)
    db.add(user)
    db.commit()
    return user


def test_create_crypto_order_records_txid_and_usd(db_session):
    user = _seed(db_session)
    order = OrderService(db_session).create_order(
        user=user,
        package_id=1,
        macro_regions=["eu"],
        payment_method="crypto",
        crypto_txid="0xabc",
        crypto_link="https://x/0xabc",
    )
    assert order.payment_method == "crypto"
    assert order.crypto_txid == "0xabc"
    assert order.receipt_file_id is None
    assert order.amount_usd_snapshot == Decimal("50.00")  # 3,000,000 / 60,000


def test_create_card_order_unchanged(db_session):
    user = _seed(db_session)
    order = OrderService(db_session).create_order(
        user=user,
        package_id=1,
        macro_regions=["eu"],
        receipt_file_id="file123",
        receipt_file_unique_id="u123",
    )
    assert order.payment_method == "card"
    assert order.receipt_file_id == "file123"
    assert order.crypto_txid is None


def test_create_order_crypto_without_reseller_address_raises(db_session):
    """#37: crypto plan order must be rejected when the reseller has no
    crypto address configured (no AdminBot row at all)."""
    user = _seed(db_session, crypto_address=None)

    with pytest.raises(OrderError):
        OrderService(db_session).create_order(
            user=user,
            package_id=1,
            macro_regions=["eu"],
            payment_method="crypto",
            crypto_txid="0xabc",
        )

    assert db_session.query(UserOrder).count() == 0
    assert user.current_order_id is None


def test_create_order_crypto_with_empty_reseller_address_raises(db_session):
    """#37: same guard when an AdminBot row exists but crypto_address is the
    empty string (bot configured for card payments only)."""
    user = _seed(db_session, crypto_address=None)
    db_session.add(
        AdminBot(
            admin_id=1,
            bot_token_enc=b"\x00" * 28,
            bot_username="r1_bot",
            bot_user_id=1,
            webhook_secret="whsecret",
            crypto_address="",
        )
    )
    db_session.commit()

    with pytest.raises(OrderError):
        OrderService(db_session).create_order(
            user=user,
            package_id=1,
            macro_regions=["eu"],
            payment_method="crypto",
            crypto_txid="0xabc",
        )

    assert db_session.query(UserOrder).count() == 0
