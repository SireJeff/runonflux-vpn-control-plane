from decimal import Decimal

from app.models.admins import Admin
from app.services.free_config.free_config_service import FreeConfigService


def _admin(db):
    a = Admin(id=1, username="r1", password_hash="x", status="active",
              wallet_balance=Decimal("0.00"))
    db.add(a); db.commit()
    return a


def test_get_or_create_is_idempotent(db_session):
    _admin(db_session)
    svc = FreeConfigService(db_session)
    fc1 = svc.get_or_create(1)
    fc2 = svc.get_or_create(1)
    assert fc1.id == fc2.id
    assert fc1.is_enabled is False


def test_update_toggles_enabled(db_session):
    _admin(db_session)
    svc = FreeConfigService(db_session)
    svc.get_or_create(1)
    fc = svc.update(1, is_enabled=True, label="Free CH", region="eu")
    assert fc.is_enabled is True
    assert fc.label == "Free CH"


def test_public_bundle_none_when_disabled(db_session):
    _admin(db_session)
    svc = FreeConfigService(db_session)
    svc.get_or_create(1)
    assert svc.public_bundle(1) is None
