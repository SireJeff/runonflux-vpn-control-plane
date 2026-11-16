"""Fix 1: WireOrderService uses Toman-per-USD division, matching the
super_admin approve endpoint convention (amount_tomans / rate)."""

from decimal import Decimal

from app.models.admins import Admin
from app.models.platform_settings import PlatformSetting
from app.services.billing.wire_order_service import WireOrderService


def _make_admin(db_session, username):
    admin = Admin(username=username, password_hash="x", status="active")
    db_session.add(admin)
    db_session.commit()
    db_session.refresh(admin)
    return admin


def test_approve_order_divides_tomans_by_toman_per_usd_rate(db_session):
    admin = _make_admin(db_session, "wire_rate_admin")
    svc = WireOrderService(db_session)
    order = svc.create_order(
        admin_id=admin.id,
        amount_tomans=Decimal("600000"),
        contact_telegram="@wire_rate",
    )
    approved = svc.approve_order(
        order.id, reviewed_by=admin.id, exchange_rate=Decimal("60000")
    )
    # 600,000 Tomans / 60,000 (Toman-per-USD) = $10.00
    # (same convention as super_admin.py:1033)
    assert approved.amount_usd == Decimal("10.00")


def test_get_exchange_rate_reads_toman_per_usd_key(db_session):
    db_session.add(PlatformSetting(key="toman_per_usd_rate", value="55000"))
    db_session.commit()
    svc = WireOrderService(db_session)
    assert svc._get_exchange_rate() == Decimal("55000")
