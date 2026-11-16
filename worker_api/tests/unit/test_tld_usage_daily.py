"""TldUsageDaily model + migration (phase 5.1). DB-backed: round-trips a row
(seeding a parent RegisteredTld to satisfy the FK) and enforces the
(snapshot_date, purpose, tld_id) unique constraint.

Run via the VM driver against fluxvpn_test (never the prod fluxvpn db).
"""
from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.registered_tld import RegisteredTld
from app.models.tld_usage_daily import TldUsageDaily


def _stub_commit(db_session, monkeypatch):
    """StaticPool reuses one connection; route commit through flush (no leak)."""
    monkeypatch.setattr(db_session, "commit", db_session.flush)


def _seed_parent_tld(db_session, domain="operator4.example.invalid"):
    """A RegisteredTld row to satisfy tld_usage_daily.tld_id FK."""
    tld = RegisteredTld(
        domain=domain, dns_provider="cloudflare", purpose="fdm", is_active=True
    )
    db_session.add(tld)
    db_session.flush()
    return tld


@pytest.mark.database
def test_tld_usage_daily_round_trips(db_session, monkeypatch):
    _stub_commit(db_session, monkeypatch)
    parent = _seed_parent_tld(db_session)
    db_session.add(
        TldUsageDaily(
            snapshot_date=date(2026, 6, 26),
            purpose="fdm",
            tld_id=parent.id,
            domain_snapshot="operator4.example.invalid",
            active_user_count=7,
        )
    )
    db_session.flush()

    got = db_session.query(TldUsageDaily).filter_by(purpose="fdm").one()
    assert got.active_user_count == 7
    assert got.domain_snapshot == "operator4.example.invalid"  # frozen, survives soft-delete
    assert got.tld_id == parent.id


@pytest.mark.database
def test_tld_usage_daily_unique_date_purpose_tld(db_session, monkeypatch):
    _stub_commit(db_session, monkeypatch)
    parent = _seed_parent_tld(db_session)
    db_session.add(
        TldUsageDaily(
            snapshot_date=date(2026, 6, 26),
            purpose="fdm",
            tld_id=parent.id,
            domain_snapshot="operator4.example.invalid",
            active_user_count=3,
        )
    )
    db_session.flush()

    # Duplicate (date, purpose, tld_id) must violate the unique constraint.
    db_session.add(
        TldUsageDaily(
            snapshot_date=date(2026, 6, 26),
            purpose="fdm",
            tld_id=parent.id,
            domain_snapshot="operator4.example.invalid",
            active_user_count=9,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
