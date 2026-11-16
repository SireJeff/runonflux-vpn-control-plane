"""TLD DNS-health gate (spec §4.1). fdm-only: assign_via_lb prefers TLDs with
>=1 healthy FdmDomain, falling back to the is_active pool when ALL are dark
(do-no-harm floor — never raises NoActiveTld where it didn't before). Non-fdm
purposes are unaffected (no health concept).

Group A (VM) DB-backed tests: @pytest.mark.database, (db_session, monkeypatch),
_stub_commit FIRST. Same scaffolding as test_fdm_sync_dns_rightsize_tld.py.
"""
import pytest

from app.models.admins import Admin
from app.models.fdm import FdmDeployment, FdmDomain
from app.models.registered_tld import RegisteredTld
from app.services.tlds.selection import TldSelectionService


def _stub_commit(db_session, monkeypatch):
    monkeypatch.setattr(db_session, "commit", db_session.flush)


def _deployment(db):
    dep = FdmDeployment(
        flux_app_name="test-app", region="CH", base_domain="x.link", domain_pool_size=2
    )
    db.add(dep)
    db.flush()
    return dep


def _tld(db, domain, *, purpose="fdm", active=True):
    t = RegisteredTld(
        domain=domain,
        dns_provider="cloudflare",
        zone_id="z-" + domain,
        purpose=purpose,
        server_ip="1.2.3.4",
        is_active=active,
    )
    db.add(t)
    db.flush()
    return t


def _domain(db, dep_id, tld_id, name, health):
    d = FdmDomain(
        deployment_id=dep_id,
        tld_id=tld_id,
        domain_name=name,
        domain_id=name.split(".")[0],
        health_status=health,
    )
    db.add(d)
    db.flush()
    return d


@pytest.mark.database
def test_assign_via_lb_prefers_healthy_fdm_tld(db_session):
    """dark.link has the lower id (would win the (count,id) tie-break without
    the gate) but 0 healthy domains; lit.link has a healthy domain and must win."""
    db = db_session
    dep = _deployment(db)
    _tld(db, "dark.link")  # id assigned first -> lower
    lit = _tld(db, "lit.link")
    _domain(db, dep.id, lit.id, "a.lit.link", "healthy")
    # no healthy domain for dark

    chosen = TldSelectionService(db).assign_via_lb("fdm")
    assert chosen.id == lit.id


@pytest.mark.database
def test_assign_via_lb_all_dark_falls_back_to_active_pool(db_session):
    """Every fdm TLD dark -> fall back to the is_active pool (do-no-harm floor).
    Must NOT raise NoActiveTld. Tie-break picks the lower id."""
    db = db_session
    _deployment(db)
    a = _tld(db, "a.link")
    _tld(db, "b.link")
    # neither has a healthy domain

    chosen = TldSelectionService(db).assign_via_lb("fdm")
    assert chosen.id == a.id  # floor preserved; min (0 users, lower id)


@pytest.mark.database
def test_assign_via_lb_non_fdm_ignores_health(db_session):
    """Subscription TLDs have NO FdmDomain rows; selection must work identically
    to today (the gate is fdm-only and is skipped entirely)."""
    db = db_session
    s = _tld(db, "sub.link", purpose="subscription")
    chosen = TldSelectionService(db).assign_via_lb("subscription")
    assert chosen.id == s.id


def _admin(db, name="adm"):
    a = Admin(username=name, password_hash="x", status="active")
    db.add(a)
    db.flush()
    return a


@pytest.mark.database
def test_set_pin_rejects_zero_healthy_fdm_tld(db_session):
    """A 0-healthy fdm TLD must be a hard-reject pin target (routes users dark)."""
    db = db_session
    _deployment(db)
    dark = _tld(db, "dark.link")  # 0 healthy domains
    adm = _admin(db)
    with pytest.raises(ValueError):
        TldSelectionService(db).set_pin(adm.id, "fdm", dark.id)


@pytest.mark.database
def test_set_pin_allows_healthy_fdm_tld(db_session):
    db = db_session
    dep = _deployment(db)
    lit = _tld(db, "lit.link")
    _domain(db, dep.id, lit.id, "a.lit.link", "healthy")
    adm = _admin(db)
    state = TldSelectionService(db).set_pin(adm.id, "fdm", lit.id)
    assert state.pinned_tld_id == lit.id
    assert state.effective_tld_id == lit.id


@pytest.mark.database
def test_set_pin_non_fdm_allows_no_domains(db_session):
    """Non-fdm TLDs have no domains / no health concept; pin must succeed."""
    db = db_session
    s = _tld(db, "sub.link", purpose="subscription")
    adm = _admin(db)
    state = TldSelectionService(db).set_pin(adm.id, "subscription", s.id)
    assert state.pinned_tld_id == s.id


@pytest.mark.database
def test_set_pin_rejects_inactive_tld(db_session):
    """Pinning to a registered-but-INACTIVE TLD must be rejected for every
    purpose: provisioning (DNS + Traefik route + fdm domains) happens only on
    activate, so an inactive target routes admins at a dead host — the
    "reassignment sticks but the domain doesn't work" bug (audit 2026-08-19)."""
    db = db_session
    s = _tld(db, "inactive.link", purpose="subscription", active=False)
    adm = _admin(db)
    with pytest.raises(ValueError):
        TldSelectionService(db).set_pin(adm.id, "subscription", s.id)
