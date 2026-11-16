"""DB-backed tests for TldSelectionService and AdminTldState.

Run in the container (db_session needs PostgreSQL). TEST_DATABASE_URL MUST
point at fluxvpn_test (never the production fluxvpn db):

  docker exec fluxvpn_worker_api sh -c '\\
      export TEST_DATABASE_URL=$(python -c "import os;u=os.environ[\\\"DATABASE_URL\\\"];print(u.replace(\\\"/fluxvpn?\\\",\\\"/fluxvpn_test?\\\") if \\\"/fluxvpn?\\\" in u else u[:-8]+\\\"fluxvpn_test\\\")");\\
      python -m pytest tests/unit/services/test_tld_selection.py -o addopts=\"\" --strict-markers -v'
"""

from datetime import datetime

import pytest

from app.models.admin_tld_state import AdminTldState
from app.models.admin_users import AdminUser
from app.models.admins import Admin
from app.models.registered_tld import RegisteredTld
from app.services.tlds.selection import NoActiveTld, TldSelectionService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _seed_active_tld(db_session, domain, purpose="subscription"):
    tld = RegisteredTld(
        domain=domain, dns_provider="cloudflare", purpose=purpose, is_active=True
    )
    db_session.add(tld)
    db_session.flush()
    return tld


def _seed_admin_with_users(
    db_session, name, effective_tld_id, n_active, purpose="subscription"
):
    adm = Admin(username=name, password_hash="x", status="active")
    db_session.add(adm)
    db_session.flush()
    if effective_tld_id is not None:
        db_session.add(
            AdminTldState(
                admin_id=adm.id,
                purpose=purpose,
                effective_tld_id=effective_tld_id,
                source="lb",
            )
        )
    for i in range(n_active):
        db_session.add(AdminUser(admin_id=adm.id, username=f"{name}_u{i}"))
    db_session.flush()
    return adm


# ---------------------------------------------------------------------------
# Task 1.1 — AdminTldState persistence
# ---------------------------------------------------------------------------


@pytest.mark.database
def test_admin_tld_state_persists(db_session):
    """AdminTldState rows round-trip through the DB with the expected shape."""
    adm = Admin(username="r1", password_hash="x", status="active")
    db_session.add(adm)
    db_session.flush()

    st = AdminTldState(admin_id=adm.id, purpose="subscription", source="unassigned")
    db_session.add(st)
    db_session.flush()

    got = db_session.query(AdminTldState).first()
    assert got is not None
    assert got.admin_id == adm.id
    assert got.purpose == "subscription"
    assert got.effective_tld_id is None
    assert got.source == "unassigned"


# ---------------------------------------------------------------------------
# Task 1.2 — RegisteredTld soft-delete + PURPOSES
# ---------------------------------------------------------------------------


@pytest.mark.database
def test_registered_tld_has_soft_delete_and_purposes(db_session):
    """deleted_at column exists and defaults to None; PURPOSES includes admin_panel."""
    tld = RegisteredTld(
        domain="x.example",
        dns_provider="cloudflare",
        purpose="admin_panel",
        is_active=False,
    )
    db_session.add(tld)
    db_session.flush()

    cols = {c.name for c in RegisteredTld.__table__.columns}
    assert "deleted_at" in cols
    assert tld.deleted_at is None
    assert "admin_panel" in RegisteredTld.PURPOSES


# ---------------------------------------------------------------------------
# Task 1.4 — active_user_counts + assign_via_lb
# ---------------------------------------------------------------------------


@pytest.mark.database
def test_active_user_counts_groups_by_effective_tld(db_session):
    tld_a = _seed_active_tld(db_session, "a.com")
    tld_b = _seed_active_tld(db_session, "b.com")
    _seed_admin_with_users(db_session, "r1", effective_tld_id=tld_a.id, n_active=3)
    _seed_admin_with_users(db_session, "r2", effective_tld_id=tld_b.id, n_active=2)

    counts = TldSelectionService(db_session).active_user_counts("subscription")

    assert counts == {tld_a.id: 3, tld_b.id: 2}


@pytest.mark.database
def test_assign_via_lb_picks_least_loaded(db_session):
    tld_a = _seed_active_tld(db_session, "a.com")
    tld_b = _seed_active_tld(db_session, "b.com")
    _seed_admin_with_users(db_session, "r1", effective_tld_id=tld_a.id, n_active=3)

    chosen = TldSelectionService(db_session).assign_via_lb("subscription")

    assert chosen.id == tld_b.id  # b has 0 active users < a's 3


@pytest.mark.database
def test_assign_via_lb_tiebreaks_by_id(db_session):
    tld_a = _seed_active_tld(db_session, "a.com")
    tld_b = _seed_active_tld(db_session, "b.com")  # both 0 users
    assert tld_a.id < tld_b.id

    chosen = TldSelectionService(db_session).assign_via_lb("subscription")

    assert chosen.id == tld_a.id  # lowest id wins ties


@pytest.mark.database
def test_assign_via_lb_excludes_tld(db_session):
    tld_a = _seed_active_tld(db_session, "a.com")
    _seed_active_tld(db_session, "b.com")

    chosen = TldSelectionService(db_session).assign_via_lb(
        "subscription", exclude_tld_id=tld_a.id
    )

    assert chosen.id != tld_a.id


@pytest.mark.database
def test_assign_via_lb_raises_when_pool_empty(db_session):
    # one INACTIVE tld -> not in pool
    db_session.add(
        RegisteredTld(
            domain="a.com",
            dns_provider="cloudflare",
            purpose="subscription",
            is_active=False,
        )
    )
    db_session.flush()

    with pytest.raises(NoActiveTld) as exc:
        TldSelectionService(db_session).assign_via_lb("subscription")
    assert exc.value.purpose == "subscription"


# ---------------------------------------------------------------------------
# Task 1.5 — resolve_effective + set_pin + clear_pin
# ---------------------------------------------------------------------------


@pytest.mark.database
def test_resolve_effective_lazy_assigns_on_first_touch(db_session):
    tld = _seed_active_tld(db_session, "a.com")
    adm = Admin(username="r1", password_hash="x", status="active")
    db_session.add(adm)
    db_session.flush()

    chosen = TldSelectionService(db_session).resolve_effective(adm.id, "subscription")

    assert chosen.id == tld.id
    st = db_session.query(AdminTldState).one()
    assert st.effective_tld_id == tld.id
    assert st.source == "lb"


@pytest.mark.database
def test_resolve_effective_sticky_on_stored_effective(db_session):
    tld = _seed_active_tld(db_session, "a.com")
    adm = Admin(username="r1", password_hash="x", status="active")
    db_session.add(adm)
    db_session.flush()
    db_session.add(
        AdminTldState(
            admin_id=adm.id,
            purpose="subscription",
            effective_tld_id=tld.id,
            source="lb",
        )
    )
    db_session.flush()

    # second resolve returns the same, no new state row
    chosen = TldSelectionService(db_session).resolve_effective(adm.id, "subscription")
    assert chosen.id == tld.id
    assert db_session.query(AdminTldState).count() == 1


@pytest.mark.database
def test_resolve_effective_self_heals_when_effective_deactivated(db_session):
    tld_a = _seed_active_tld(db_session, "a.com")
    tld_b = _seed_active_tld(db_session, "b.com")
    adm = Admin(username="r1", password_hash="x", status="active")
    db_session.add(adm)
    db_session.flush()
    # stored effective is tld_a, but tld_a is now inactive
    db_session.add(
        AdminTldState(
            admin_id=adm.id,
            purpose="subscription",
            effective_tld_id=tld_a.id,
            source="lb",
        )
    )
    db_session.flush()
    tld_a.is_active = False
    db_session.flush()

    chosen = TldSelectionService(db_session).resolve_effective(adm.id, "subscription")

    assert chosen.id == tld_b.id  # self-healed to the only active TLD
    st = db_session.query(AdminTldState).one()
    assert st.effective_tld_id == tld_b.id


@pytest.mark.database
def test_resolve_effective_self_heals_when_effective_soft_deleted(db_session):
    """Soft-deleted (deleted_at set) effective must also self-heal (delete path)."""
    tld_a = _seed_active_tld(db_session, "a.com")
    tld_b = _seed_active_tld(db_session, "b.com")
    adm = Admin(username="r1", password_hash="x", status="active")
    db_session.add(adm)
    db_session.flush()
    db_session.add(
        AdminTldState(
            admin_id=adm.id,
            purpose="subscription",
            effective_tld_id=tld_a.id,
            source="lb",
        )
    )
    db_session.flush()
    # tld_a still is_active=True but soft-deleted (tombstoned)
    tld_a.deleted_at = datetime(2026, 6, 25)
    db_session.flush()

    chosen = TldSelectionService(db_session).resolve_effective(adm.id, "subscription")

    assert chosen.id == tld_b.id
    st = db_session.query(AdminTldState).one()
    assert st.effective_tld_id == tld_b.id


@pytest.mark.database
def test_set_pin_updates_pinned_and_effective(db_session):
    tld = _seed_active_tld(db_session, "a.com")
    adm = Admin(username="r1", password_hash="x", status="active")
    db_session.add(adm)
    db_session.flush()

    TldSelectionService(db_session).set_pin(adm.id, "subscription", tld.id)

    st = db_session.query(AdminTldState).one()
    assert st.pinned_tld_id == tld.id
    assert st.effective_tld_id == tld.id
    assert st.source == "pin"


@pytest.mark.database
def test_set_pin_rejects_soft_deleted_tld(db_session):
    """Pinning to a soft-deleted TLD must raise ValueError (set_pin guard)."""
    tld = _seed_active_tld(db_session, "a.com")
    tld.deleted_at = datetime(2026, 6, 25)
    db_session.flush()
    adm = Admin(username="r1", password_hash="x", status="active")
    db_session.add(adm)
    db_session.flush()

    with pytest.raises(ValueError):
        TldSelectionService(db_session).set_pin(adm.id, "subscription", tld.id)


@pytest.mark.database
def test_clear_pin_recomputes_effective_via_lb(db_session):
    tld_a = _seed_active_tld(db_session, "a.com")
    tld_b = _seed_active_tld(db_session, "b.com")
    adm = Admin(username="r1", password_hash="x", status="active")
    db_session.add(adm)
    db_session.flush()
    # pinned to a
    db_session.add(
        AdminTldState(
            admin_id=adm.id,
            purpose="subscription",
            pinned_tld_id=tld_a.id,
            effective_tld_id=tld_a.id,
            source="pin",
        )
    )
    db_session.flush()

    TldSelectionService(db_session).clear_pin(adm.id, "subscription")

    st = db_session.query(AdminTldState).one()
    assert st.pinned_tld_id is None
    assert st.source == "lb"
    # tie -> lowest id wins
    assert st.effective_tld_id == min(tld_a.id, tld_b.id)


# ---------------------------------------------------------------------------
# Task 1.6 — migrate_off
# ---------------------------------------------------------------------------


@pytest.mark.database
def test_migrate_off_reassigns_effective(db_session):
    tld_a = _seed_active_tld(db_session, "a.com")
    tld_b = _seed_active_tld(db_session, "b.com")
    adm = Admin(username="r1", password_hash="x", status="active")
    db_session.add(adm)
    db_session.flush()
    db_session.add(
        AdminTldState(
            admin_id=adm.id,
            purpose="subscription",
            effective_tld_id=tld_a.id,
            source="lb",
        )
    )
    db_session.flush()

    affected, cleared = TldSelectionService(db_session).migrate_off(tld_a.id)

    assert len(affected) == 1
    admin_id, purpose, old_domain, new_domain = affected[0]
    assert admin_id == adm.id and purpose == "subscription"
    assert old_domain == "a.com" and new_domain == "b.com"
    assert cleared == []
    st = db_session.query(AdminTldState).one()
    assert st.effective_tld_id == tld_b.id
    assert st.source == "lb"


@pytest.mark.database
def test_migrate_off_preserves_pin_by_default(db_session):
    """Deactivate path: pin survives; only effective moves (spec D8)."""
    tld_a = _seed_active_tld(db_session, "a.com")
    tld_b = _seed_active_tld(db_session, "b.com")
    adm = Admin(username="r1", password_hash="x", status="active")
    db_session.add(adm)
    db_session.flush()
    db_session.add(
        AdminTldState(
            admin_id=adm.id,
            purpose="subscription",
            pinned_tld_id=tld_a.id,
            effective_tld_id=tld_a.id,
            source="pin",
        )
    )
    db_session.flush()

    affected, cleared = TldSelectionService(db_session).migrate_off(
        tld_a.id, clear_pinned=False
    )

    assert cleared == []
    st = db_session.query(AdminTldState).one()
    assert st.pinned_tld_id == tld_a.id  # pin preserved
    assert st.effective_tld_id == tld_b.id  # effective moved


@pytest.mark.database
def test_migrate_off_clears_pin_when_requested(db_session):
    """Delete path: dangling pin cleared and reported (spec D8)."""
    tld_a = _seed_active_tld(db_session, "a.com")
    tld_b = _seed_active_tld(db_session, "b.com")
    adm = Admin(username="r1", password_hash="x", status="active")
    db_session.add(adm)
    db_session.flush()
    db_session.add(
        AdminTldState(
            admin_id=adm.id,
            purpose="subscription",
            pinned_tld_id=tld_a.id,
            effective_tld_id=tld_a.id,
            source="pin",
        )
    )
    db_session.flush()

    affected, cleared = TldSelectionService(db_session).migrate_off(
        tld_a.id, clear_pinned=True
    )

    assert cleared == [(adm.id, "subscription")]
    st = db_session.query(AdminTldState).one()
    assert st.pinned_tld_id is None
    assert st.effective_tld_id == tld_b.id


@pytest.mark.database
def test_migrate_off_noop_when_no_state_references_tld(db_session):
    tld_a = _seed_active_tld(db_session, "a.com")
    _seed_active_tld(db_session, "b.com")  # needed so LB has a target if called
    affected, cleared = TldSelectionService(db_session).migrate_off(tld_a.id)
    assert affected == [] and cleared == []


@pytest.mark.database
def test_migrate_off_raises_when_only_active_tld(db_session):
    """Migrating off the only active TLD raises NoActiveTld (deactivate/delete
    endpoints in Phase 2 guard against this with a last-active check). No partial
    state is flushed: the raise precedes the single end-of-method flush."""
    tld_a = _seed_active_tld(db_session, "a.com")  # the only active TLD
    adm = Admin(username="r1", password_hash="x", status="active")
    db_session.add(adm)
    db_session.flush()
    db_session.add(
        AdminTldState(
            admin_id=adm.id,
            purpose="subscription",
            effective_tld_id=tld_a.id,
            source="lb",
        )
    )
    db_session.flush()

    with pytest.raises(NoActiveTld) as exc:
        TldSelectionService(db_session).migrate_off(tld_a.id)
    assert exc.value.purpose == "subscription"


# ---------------------------------------------------------------------------
# Task 2 (Phase 2) — race-safe create path in _store_assignment
# ---------------------------------------------------------------------------


@pytest.mark.database
def test_store_assignment_idempotent_under_duplicate(db_session):
    """Two sequential _store_assignment calls for the same (admin, purpose)
    must not raise IntegrityError and must leave exactly one state row whose
    effective is the LB pick. (Simulates the loser-after-winner path.)"""
    _seed_active_tld(db_session, "a.com")
    _seed_active_tld(db_session, "b.com")
    adm = Admin(username="r1", password_hash="x", status="active")
    db_session.add(adm)
    db_session.flush()

    svc = TldSelectionService(db_session)
    first = svc._store_assignment(adm.id, "subscription", pinned_tld_id=None)
    # Second call: a row already exists — must re-query, not re-insert.
    second = svc._store_assignment(adm.id, "subscription", pinned_tld_id=None)

    assert first.id == second.id  # same effective TLD (sticky)
    assert db_session.query(AdminTldState).count() == 1


@pytest.mark.database
def test_resolve_effective_concurrent_first_touch_no_integrity_error(db_session):
    """resolve_effective twice on a fresh admin does not raise; one state row."""
    _seed_active_tld(db_session, "a.com")
    adm = Admin(username="r1", password_hash="x", status="active")
    db_session.add(adm)
    db_session.flush()

    svc = TldSelectionService(db_session)
    a = svc.resolve_effective(adm.id, "subscription")
    b = svc.resolve_effective(adm.id, "subscription")

    assert a.id == b.id
    assert db_session.query(AdminTldState).count() == 1
