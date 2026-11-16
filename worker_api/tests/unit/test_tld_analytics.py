"""TldUsageDaily snapshot beat task (phase 5.2). DB-backed: the written rows
MUST equal active_user_counts (drift-proof) and prune must drop >90-day rows.

Run via the VM driver against fluxvpn_test (never the prod fluxvpn db).
"""
from datetime import date, timedelta

import pytest

from app.models.admin_tld_state import AdminTldState
from app.models.admin_users import AdminUser
from app.models.admins import Admin
from app.models.registered_tld import RegisteredTld
from app.models.tld_usage_daily import TldUsageDaily
from app.services.tlds.selection import TldSelectionService
from app.tasks.tld_analytics import run_tld_snapshot


def _stub_commit(db_session, monkeypatch):
    monkeypatch.setattr(db_session, "commit", db_session.flush)


def _seed_tld(db, domain, purpose="fdm", active=True):
    tld = RegisteredTld(
        domain=domain, dns_provider="cloudflare", purpose=purpose, is_active=active
    )
    db.add(tld)
    db.flush()
    return tld


def _seed_admin_with_users(db, name, tld_id, n_active, purpose="fdm"):
    adm = Admin(username=name, password_hash="x", status="active")
    db.add(adm)
    db.flush()
    db.add(
        AdminTldState(
            admin_id=adm.id, purpose=purpose, effective_tld_id=tld_id, source="lb"
        )
    )
    for i in range(n_active):
        db.add(AdminUser(admin_id=adm.id, username=f"{name}_u{i}"))
    db.flush()
    return adm


@pytest.mark.database
def test_snapshot_writes_counts_matching_active_user_counts(db_session, monkeypatch):
    _stub_commit(db_session, monkeypatch)
    today = date(2026, 6, 26)
    a = _seed_tld(db_session, "a.com", "fdm")
    b = _seed_tld(db_session, "b.com", "fdm")
    _seed_admin_with_users(db_session, "ra", a.id, 3)
    _seed_admin_with_users(db_session, "rb", b.id, 2)

    deleted = run_tld_snapshot(db_session, today=today)
    assert deleted == 0

    # Drift-proof: snapshot rows == the LB's active_user_counts view.
    counts = TldSelectionService(db_session).active_user_counts("fdm")
    rows = {
        r.tld_id: r.active_user_count
        for r in db_session.query(TldUsageDaily)
        .filter_by(snapshot_date=today, purpose="fdm")
        .all()
    }
    assert rows == counts  # {a.id: 3, b.id: 2}
    assert (
        db_session.query(TldUsageDaily).filter_by(tld_id=a.id).one().domain_snapshot
        == "a.com"
    )


@pytest.mark.database
def test_snapshot_is_idempotent_same_day(db_session, monkeypatch):
    _stub_commit(db_session, monkeypatch)
    today = date(2026, 6, 26)
    tld = _seed_tld(db_session, "a.com", "fdm")
    _seed_admin_with_users(db_session, "ra", tld.id, 4)

    run_tld_snapshot(db_session, today=today)
    run_tld_snapshot(db_session, today=today)  # re-run same day

    rows = (
        db_session.query(TldUsageDaily)
        .filter_by(snapshot_date=today, purpose="fdm")
        .all()
    )
    assert len(rows) == 1  # upsert, not duplicate
    assert rows[0].active_user_count == 4


@pytest.mark.database
def test_snapshot_prunes_rows_older_than_retention(db_session, monkeypatch):
    _stub_commit(db_session, monkeypatch)
    today = date(2026, 6, 26)
    tld = _seed_tld(db_session, "a.com", "subscription")
    db_session.add(
        TldUsageDaily(
            snapshot_date=today - timedelta(days=100),
            purpose="subscription",
            tld_id=tld.id,
            domain_snapshot="a.com",
            active_user_count=1,
        )
    )
    db_session.add(
        TldUsageDaily(
            snapshot_date=today - timedelta(days=10),
            purpose="subscription",
            tld_id=tld.id,
            domain_snapshot="a.com",
            active_user_count=1,
        )
    )
    db_session.flush()

    deleted = run_tld_snapshot(db_session, today=today)
    assert deleted == 1  # only the 100-day-old row pruned

    remaining = db_session.query(TldUsageDaily).filter_by(tld_id=tld.id).all()
    cutoff = today - timedelta(days=90)
    assert all(r.snapshot_date >= cutoff for r in remaining)
    assert len(remaining) == 2  # today's upsert + the 10-day-old row


@pytest.mark.database
def test_snapshot_includes_deactivated_tld_with_lingering_users(
    db_session, monkeypatch
):
    """Migration tail (spec point 2): a DEACTIVATED TLD (is_active=False but
    deleted_at=None) that still has admins effectively assigned to it (not yet
    migrated off) must still get a snapshot row — so the migration shows in
    history. Distinct from a soft-DELETED TLD, which is skipped."""
    _stub_commit(db_session, monkeypatch)
    today = date(2026, 6, 26)
    # is_active=False but deleted_at stays None -> deactivated, not deleted.
    inactive = RegisteredTld(
        domain="old.com", dns_provider="cloudflare", purpose="fdm", is_active=False
    )
    db_session.add(inactive)
    db_session.flush()
    # An admin still effectively riding the deactivated TLD (lingering assignment).
    _seed_admin_with_users(db_session, "rtail", inactive.id, 2)

    run_tld_snapshot(db_session, today=today)

    # active_user_counts counts it (effective_tld_id join ignores is_active),
    # so the snapshot's `counts.keys()` tail writes a row for it.
    row = (
        db_session.query(TldUsageDaily)
        .filter_by(snapshot_date=today, purpose="fdm", tld_id=inactive.id)
        .one()
    )
    assert row.active_user_count == 2
    assert row.domain_snapshot == "old.com"
