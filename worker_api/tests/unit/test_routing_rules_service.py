import sys
from unittest.mock import MagicMock

# Mock cloudflare before importing app modules
sys.modules.setdefault("cloudflare", MagicMock())
sys.modules.setdefault("cloudflare.types", MagicMock())
sys.modules.setdefault("cloudflare.types.dns", MagicMock())

from decimal import Decimal

from app.models.admins import Admin
from app.services.routing.routing_rules_service import RoutingRulesService


def _admin(db, admin_id=1):
    a = Admin(id=admin_id, username=f"r{admin_id}", password_hash="x",
              status="active", wallet_balance=Decimal("0.00"))
    db.add(a)
    db.commit()
    return a


def test_get_or_create_makes_disabled_default(db_session):
    _admin(db_session)
    svc = RoutingRulesService(db_session)
    cfg = svc.get_or_create(admin_id=1)
    assert cfg.is_enabled is False
    assert cfg.rules == {}
    # idempotent
    assert svc.get_or_create(admin_id=1).id == cfg.id


def test_replace_sets_rules_and_enabled(db_session):
    _admin(db_session)
    svc = RoutingRulesService(db_session)
    cfg = svc.replace(
        admin_id=1, is_enabled=True,
        ban_domains=["ads.com"], allow_domains=["bank.ir"],
        presets={"iran_direct": True},
    )
    assert cfg.is_enabled is True
    assert cfg.rules == {
        "ban_domains": ["ads.com"],
        "allow_domains": ["bank.ir"],
        "presets": {"iran_direct": True},
    }


def test_get_effective_rules_empty_when_disabled(db_session):
    _admin(db_session)
    svc = RoutingRulesService(db_session)
    svc.replace(admin_id=1, is_enabled=False, ban_domains=["ads.com"],
                allow_domains=[], presets={})
    assert svc.get_effective_rules(admin_id=1) == {}


def test_get_effective_rules_returns_rules_when_enabled(db_session):
    _admin(db_session)
    svc = RoutingRulesService(db_session)
    svc.replace(admin_id=1, is_enabled=True, ban_domains=["ads.com"],
                allow_domains=[], presets={})
    assert svc.get_effective_rules(admin_id=1)["ban_domains"] == ["ads.com"]


def test_get_effective_rules_empty_when_no_row(db_session):
    assert RoutingRulesService(db_session).get_effective_rules(admin_id=999) == {}
