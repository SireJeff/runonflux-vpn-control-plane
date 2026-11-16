from datetime import datetime, timezone
from decimal import Decimal

from app.models.admin_users import AdminUser
from app.models.admins import Admin
from app.models.admin_packages import AdminPackage
from app.models.free_config_enrollment import FreeConfigEnrollment
from app.models.user_orders import UserOrder
from app.services.orders.order_service import OrderService


def _seed(db):
    a = Admin(id=1, username="r1", password_hash="x", status="active",
              wallet_balance=Decimal("0.00"))
    db.add(a); db.flush()
    u = AdminUser(id=1, admin_id=1, username="u1", password_hash="x",
                  status="pending")
    db.add(u); db.flush()
    o = UserOrder(id=1, user_id=1, admin_id=1, kind="subscription",
                  package_snapshot={"name": "Basic", "traffic_gb": 50,
                                    "duration_days": 30, "price_tomans": 300000},
                  macro_region="eu", macro_regions=["eu"],
                  amount_tomans=Decimal("300000"), status="pending")
    db.add(o); db.commit()
    return u, o


def test_activate_sets_traffic_and_status(db_session, monkeypatch):
    # Avoid external side effects: stub region + credential + delivery.
    import app.services.orders.order_service as mod
    monkeypatch.setattr(mod, "set_user_regions", lambda *a, **k: None)
    monkeypatch.setattr("app.services.regions.availability.healthy_macro_codes",
                        lambda db: ["eu"])
    u, o = _seed(db_session)
    svc = OrderService(db_session)
    svc._activate_subscription(o, u, datetime.now(timezone.utc).replace(tzinfo=None))
    assert u.status == "active"
    assert u.traffic_limit_bytes == int(50 * 1024**3)
    assert u.expires_at is not None


def test_activate_revokes_free_config_enrollment(db_session, monkeypatch):
    # A user who claimed a free config and later buys a paid plan must lose
    # the free-config enrollment marker, otherwise the nightly free-quota
    # reset re-clobbers their paid traffic limit.
    import app.services.orders.order_service as mod
    monkeypatch.setattr(mod, "set_user_regions", lambda *a, **k: None)
    monkeypatch.setattr("app.services.regions.availability.healthy_macro_codes",
                        lambda db: ["eu"])
    u, o = _seed(db_session)
    db_session.add(FreeConfigEnrollment(user_id=u.id, admin_id=u.admin_id,
                                        membership_ok=True))
    db_session.commit()

    svc = OrderService(db_session)
    svc._activate_subscription(o, u, datetime.now(timezone.utc).replace(tzinfo=None))
    db_session.flush()

    remaining = (
        db_session.query(FreeConfigEnrollment).filter_by(user_id=u.id).count()
    )
    assert remaining == 0
