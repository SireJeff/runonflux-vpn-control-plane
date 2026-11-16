"""Phase 2 — TLD lifecycle endpoint + schema tests.

Covers the multi-active TLD feature: admin_panel purpose, activate→ADD,
deactivate (last-active guard + migrate_off), and delete→soft-delete.

DB-backed tests in this module run on the VM ``fluxvpn_test`` db — never prod
``fluxvpn`` (see the plan's Global Constraints + memory
``multi_tld_management_2026-06-25.md``). The Task 1 schema tests below need no
DB.

Note: located flat under ``tests/unit/`` to match the existing convention
(sibling ``test_super_admin_tld.py``); the plan named an ``tests/unit/api/``
subdir, but this codebase keeps unit tests flat.
"""

import asyncio

import pytest

from app.schemas.super_admin import TldCreateRequest, TldListResponse


def _stub_commit(db_session, monkeypatch):
    """Map session.commit -> flush so committing lifecycle helpers don't persist
    beyond this test. db_session isolates via an outer transaction rolled back
    at teardown; a real commit would commit that transaction and leak rows into
    later tests in the same run (StaticPool reuses one connection; the schema is
    only reset between runs, not between tests)."""
    monkeypatch.setattr(db_session, "commit", db_session.flush)


@pytest.fixture(autouse=True)
def _neutralize_tld_notice_enqueue(monkeypatch):
    """Neutralize the end-user TLD-notice Celery enqueue for every test in this
    module. As of Phase 3, deactivate/delete fan out via _notify_tld_migration ->
    notify_end_users_tld_changed.delay(...); a REAL enqueue could be picked up by
    the live Celery worker and message production users with the test's fake
    domains. Tests that ASSERT on the enqueue install their own fake (which
    overrides this — same function-scoped monkeypatch, later setattr wins). If
    the task module cannot be imported there is nothing to neutralize (the
    endpoint's lazy import would fail and be swallowed too)."""

    class _NoOpTask:
        @staticmethod
        def delay(*args, **kwargs):
            return None

    try:
        import app.tasks.end_user_notifications as _tasks
    except Exception:
        return
    monkeypatch.setattr(_tasks, "notify_end_users_tld_changed", _NoOpTask)


# ---------------------------------------------------------------------------
# Task 1 — admin_panel purpose + TldListResponse shape
# ---------------------------------------------------------------------------


def test_tld_create_request_accepts_admin_panel():
    req = TldCreateRequest(
        domain="panel.example",
        dns_provider="cloudflare",
        zone_id="ZID",
        purpose="admin_panel",
    )
    assert req.purpose == "admin_panel"


def test_tld_create_request_rejects_unknown_purpose():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        TldCreateRequest(
            domain="x.example",
            dns_provider="cloudflare",
            zone_id="ZID",
            purpose="nope",
        )


def test_tld_list_response_has_admin_panel_field():
    resp = TldListResponse()
    assert resp.admin_panel == []


# ---------------------------------------------------------------------------
# Task 4 — multi-active activation (activate -> ADD to pool)
# ---------------------------------------------------------------------------


@pytest.mark.database
def test_activate_second_subscription_tld_keeps_first_active(db_session, monkeypatch):
    """Multi-active: activating a 2nd subscription TLD must NOT deactivate the
    1st and must NOT write platform_settings (effective drives URLs now)."""
    from app.api.v1.endpoints import super_admin as sa
    from app.models.platform_settings import PlatformSetting
    from app.models.registered_tld import RegisteredTld

    _stub_commit(db_session, monkeypatch)

    class _FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def ensure_record_exists(self, **kw):
            return None

    monkeypatch.setattr(sa, "create_dns_client", lambda **kw: _FakeClient())

    a = RegisteredTld(
        domain="a.com",
        dns_provider="cloudflare",
        zone_id="Z",
        purpose="subscription",
        is_active=True,
        server_ip="1.2.3.4",
    )
    b = RegisteredTld(
        domain="b.com",
        dns_provider="cloudflare",
        zone_id="Z",
        purpose="subscription",
        is_active=False,
        server_ip="1.2.3.4",
    )
    db_session.add_all([a, b])
    db_session.flush()

    asyncio.run(sa._activate_subscription_tld(db_session, b, None))

    db_session.refresh(a)
    db_session.refresh(b)
    assert a.is_active is True  # NOT flipped off (multi-active)
    assert b.is_active is True
    sub_setting = (
        db_session.query(PlatformSetting)
        .filter(PlatformSetting.key == "subscription_base_url")
        .first()
    )
    assert sub_setting is None or "b.com" not in (sub_setting.value or "")


# ---------------------------------------------------------------------------
# Task 5 — deactivate endpoint (last-active guard + migrate_off, pins preserved)
# ---------------------------------------------------------------------------


@pytest.mark.database
def test_deactivate_last_active_tld_returns_409(db_session, monkeypatch):
    """Guard: deactivating the only active TLD for a purpose returns 409."""
    from fastapi import HTTPException

    from app.api.v1.endpoints import super_admin as sa
    from app.models.registered_tld import RegisteredTld

    _stub_commit(db_session, monkeypatch)

    a = RegisteredTld(
        domain="a.com",
        dns_provider="cloudflare",
        zone_id="Z",
        purpose="subscription",
        is_active=True,
        server_ip="1.2.3.4",
    )
    db_session.add(a)
    db_session.flush()

    with pytest.raises(HTTPException) as exc:
        asyncio.run(sa.deactivate_tld(a.id, db=db_session, current={"id": 1}))
    assert exc.value.status_code == 409


@pytest.mark.database
def test_deactivate_migrates_admins_and_preserves_pin(db_session, monkeypatch):
    """Deactivate: admins on the TLD migrate off (effective moves); the pin is
    preserved (spec D8)."""
    from app.api.v1.endpoints import super_admin as sa
    from app.models.admin_tld_state import AdminTldState
    from app.models.admins import Admin
    from app.models.registered_tld import RegisteredTld

    _stub_commit(db_session, monkeypatch)

    a = RegisteredTld(
        domain="a.com",
        dns_provider="cloudflare",
        zone_id="Z",
        purpose="subscription",
        is_active=True,
        server_ip="1.2.3.4",
    )
    b = RegisteredTld(
        domain="b.com",
        dns_provider="cloudflare",
        zone_id="Z",
        purpose="subscription",
        is_active=True,
        server_ip="1.2.3.4",
    )
    db_session.add_all([a, b])
    db_session.flush()
    adm = Admin(username="r1", password_hash="x", status="active")
    db_session.add(adm)
    db_session.flush()
    db_session.add(
        AdminTldState(
            admin_id=adm.id,
            purpose="subscription",
            pinned_tld_id=a.id,
            effective_tld_id=a.id,
            source="pin",
        )
    )
    db_session.flush()

    resp = asyncio.run(sa.deactivate_tld(a.id, db=db_session, current={"id": 1}))

    db_session.refresh(a)
    st = db_session.query(AdminTldState).one()
    assert a.is_active is False
    assert resp.success is True
    assert st.pinned_tld_id == a.id  # pin preserved (D8)
    assert st.effective_tld_id == b.id  # effective migrated off a


# ---------------------------------------------------------------------------
# Task 6 — delete -> soft-delete (+ migrate, clear pins, remove DNS)
# ---------------------------------------------------------------------------


@pytest.mark.database
def test_delete_active_tld_soft_deletes_and_clears_pin(db_session, monkeypatch):
    """Delete an active TLD: guard passes (2 active), admins migrate off, pin is
    CLEARED (spec D8 delete path), DNS removed, deleted_at set (never hard-delete)."""
    from app.api.v1.endpoints import super_admin as sa
    from app.models.admin_tld_state import AdminTldState
    from app.models.admins import Admin
    from app.models.registered_tld import RegisteredTld

    _stub_commit(db_session, monkeypatch)

    class _FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def find_a_record_by_name(self, name):
            return {"id": "rec-1"}

        async def delete_dns_record(self, rid):
            return None

    monkeypatch.setattr(sa, "create_dns_client", lambda **kw: _FakeClient())

    a = RegisteredTld(
        domain="a.com",
        dns_provider="cloudflare",
        zone_id="Z",
        purpose="subscription",
        is_active=True,
        server_ip="1.2.3.4",
    )
    b = RegisteredTld(
        domain="b.com",
        dns_provider="cloudflare",
        zone_id="Z",
        purpose="subscription",
        is_active=True,
        server_ip="1.2.3.4",
    )
    db_session.add_all([a, b])
    db_session.flush()
    adm = Admin(username="r1", password_hash="x", status="active")
    db_session.add(adm)
    db_session.flush()
    db_session.add(
        AdminTldState(
            admin_id=adm.id,
            purpose="subscription",
            pinned_tld_id=a.id,
            effective_tld_id=a.id,
            source="pin",
        )
    )
    db_session.flush()

    resp = asyncio.run(sa.delete_tld(a.id, db=db_session, current={"id": 1}))

    db_session.refresh(a)
    st = db_session.query(AdminTldState).one()
    assert resp["success"] is True
    assert a.deleted_at is not None  # soft-deleted (row remains)
    assert a.is_active is False
    assert st.pinned_tld_id is None  # pin cleared (D8 delete path)
    assert st.effective_tld_id == b.id  # migrated off a


@pytest.mark.database
def test_delete_inactive_tld_soft_deletes_directly(db_session, monkeypatch):
    """Deleting an already-inactive TLD skips migration and just tombstones it."""
    from app.api.v1.endpoints import super_admin as sa
    from app.models.registered_tld import RegisteredTld

    _stub_commit(db_session, monkeypatch)

    class _FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def find_a_record_by_name(self, name):
            return None

        async def delete_dns_record(self, rid):
            return None

    monkeypatch.setattr(sa, "create_dns_client", lambda **kw: _FakeClient())

    a = RegisteredTld(
        domain="a.com",
        dns_provider="cloudflare",
        zone_id="Z",
        purpose="subscription",
        is_active=False,
        server_ip="1.2.3.4",
    )
    db_session.add(a)
    db_session.flush()

    asyncio.run(sa.delete_tld(a.id, db=db_session, current={"id": 1}))

    db_session.refresh(a)
    assert a.deleted_at is not None


# ---------------------------------------------------------------------------
# Task 7 — pin endpoint (set / clear)
# ---------------------------------------------------------------------------


@pytest.mark.database
def test_pin_endpoint_sets_and_clears(db_session, monkeypatch):
    """POST /super/settings/tlds/pin: tld_id set pins the admin; tld_id=None
    clears the pin and reverts effective to LB."""
    from app.api.v1.endpoints import super_admin as sa
    from app.models.admin_tld_state import AdminTldState
    from app.models.admins import Admin
    from app.models.registered_tld import RegisteredTld
    from app.schemas.super_admin import TldPinRequest

    _stub_commit(db_session, monkeypatch)

    a = RegisteredTld(
        domain="a.com",
        dns_provider="cloudflare",
        zone_id="Z",
        purpose="subscription",
        is_active=True,
        server_ip="1.2.3.4",
    )
    b = RegisteredTld(
        domain="b.com",
        dns_provider="cloudflare",
        zone_id="Z",
        purpose="subscription",
        is_active=True,
        server_ip="1.2.3.4",
    )
    db_session.add_all([a, b])
    db_session.flush()
    adm = Admin(username="r1", password_hash="x", status="active")
    db_session.add(adm)
    db_session.flush()

    # Pin to a.
    resp = asyncio.run(
        sa.set_tld_pin(
            TldPinRequest(admin_id=adm.id, purpose="subscription", tld_id=a.id),
            db=db_session,
            current={"id": 1},
        )
    )
    assert resp["pinned_tld_id"] == a.id
    st = db_session.query(AdminTldState).one()
    assert st.pinned_tld_id == a.id
    assert st.effective_tld_id == a.id
    assert st.source == "pin"

    # Clear the pin -> effective reverts to LB (tie -> lowest id).
    resp = asyncio.run(
        sa.set_tld_pin(
            TldPinRequest(admin_id=adm.id, purpose="subscription", tld_id=None),
            db=db_session,
            current={"id": 1},
        )
    )
    assert resp["pinned_tld_id"] is None
    db_session.refresh(st)
    assert st.pinned_tld_id is None
    assert st.source == "lb"


# ---------------------------------------------------------------------------
# Task 3 (Phase 3) — targeted reseller-bot notice helper
# ---------------------------------------------------------------------------


@pytest.mark.database
def test_notify_resellers_targets_only_affected_admins(db_session, monkeypatch):
    """Only admins in `affected` get a reseller alert; unaffected admins hear nothing."""
    from app.api.v1.endpoints import super_admin as sa
    from app.models.admin_users import AdminUser
    from app.models.admins import Admin

    sent_to = []
    monkeypatch.setattr(
        "app.services.notifications.send_alert.send_telegram_alert",
        lambda tg_id, msg: (sent_to.append(tg_id) or True),
    )
    # silence the end-user task enqueue path (not under test here)
    monkeypatch.setattr(sa, "_enqueue_end_user_tld_notice", lambda *a, **k: None)

    a = Admin(username="ra", password_hash="x", status="active", telegram_id="111")
    b = Admin(username="rb", password_hash="x", status="active", telegram_id="222")
    db_session.add_all([a, b])
    db_session.flush()
    # one active user under each admin (drives the "N users moved" count)
    db_session.add_all(
        [
            AdminUser(admin_id=a.id, username="ua"),
            AdminUser(admin_id=b.id, username="ub"),
        ]
    )
    db_session.flush()

    affected = [(a.id, "subscription", "old.example", "new.example")]
    n = sa._notify_resellers_tld_change(db_session, affected, [], "deactivated")

    assert n == 1
    assert sent_to == [111]  # only affected admin A


@pytest.mark.database
def test_notify_resellers_includes_moved_count_and_pin_addendum(
    db_session, monkeypatch
):
    from app.api.v1.endpoints import super_admin as sa
    from app.models.admin_users import AdminUser
    from app.models.admins import Admin

    captured = {}

    def _capture(tg_id, msg):
        captured[tg_id] = msg
        return True

    monkeypatch.setattr(
        "app.services.notifications.send_alert.send_telegram_alert",
        _capture,
    )
    monkeypatch.setattr(sa, "_enqueue_end_user_tld_notice", lambda *a, **k: None)

    a = Admin(username="ra", password_hash="x", status="active", telegram_id="111")
    db_session.add(a)
    db_session.flush()
    db_session.add_all(
        [
            AdminUser(admin_id=a.id, username="u1"),
            AdminUser(admin_id=a.id, username="u2"),
            AdminUser(admin_id=a.id, username="u3"),
        ]
    )
    db_session.flush()

    affected = [(a.id, "subscription", "old.example", "new.example")]
    cleared = [(a.id, "subscription")]
    sa._notify_resellers_tld_change(db_session, affected, cleared, "deleted")

    msg = captured[111]
    assert "old.example" in msg
    assert "new.example" in msg
    assert "deleted" in msg
    assert "3" in msg  # 3 active users moved
    assert "pin" in msg.lower()  # cleared-pin addendum


# ---------------------------------------------------------------------------
# Task 4 (Phase 3) — wire notifications into deactivate + delete
# ---------------------------------------------------------------------------


@pytest.mark.database
def test_deactivate_notifies_affected_admins_only(db_session, monkeypatch):
    """Deactivating TLD1 notifies admin A (on TLD1) and NOT admin B (on TLD2)."""
    from app.api.v1.endpoints import super_admin as sa
    from app.models.admin_tld_state import AdminTldState
    from app.models.admins import Admin
    from app.models.registered_tld import RegisteredTld

    _stub_commit(db_session, monkeypatch)

    enqueued = []
    reseller_sent_to = []
    monkeypatch.setattr(
        "app.services.notifications.send_alert.send_telegram_alert",
        lambda tg_id, msg: (reseller_sent_to.append(tg_id) or True),
    )

    class _FakeTask:
        @staticmethod
        def delay(admin_ids, purpose, new_domain, old_domain=None):
            enqueued.append((tuple(admin_ids), purpose, new_domain, old_domain))

    monkeypatch.setattr(
        "app.tasks.end_user_notifications.notify_end_users_tld_changed",
        _FakeTask,
    )

    t1 = RegisteredTld(
        domain="old.example",
        dns_provider="cloudflare",
        zone_id="Z",
        purpose="subscription",
        is_active=True,
        server_ip="1.2.3.4",
    )
    t2 = RegisteredTld(
        domain="new.example",
        dns_provider="cloudflare",
        zone_id="Z",
        purpose="subscription",
        is_active=True,
        server_ip="1.2.3.4",
    )
    db_session.add_all([t1, t2])
    db_session.flush()
    a = Admin(username="ra", password_hash="x", status="active", telegram_id="111")
    b = Admin(username="rb", password_hash="x", status="active", telegram_id="222")
    db_session.add_all([a, b])
    db_session.flush()
    db_session.add_all(
        [
            AdminTldState(
                admin_id=a.id,
                purpose="subscription",
                effective_tld_id=t1.id,
                source="lb",
            ),
            AdminTldState(
                admin_id=b.id,
                purpose="subscription",
                effective_tld_id=t2.id,
                source="lb",
            ),
        ]
    )
    db_session.flush()

    asyncio.run(sa.deactivate_tld(t1.id, db=db_session, current={"id": 1}))

    # Admin A migrated (was on t1); admin B untouched (was on t2).
    assert len(enqueued) == 1
    admin_ids_arg, purpose, new_domain, old_domain = enqueued[0]
    assert a.id in admin_ids_arg and b.id not in admin_ids_arg
    assert purpose == "subscription"
    assert new_domain == "new.example"
    assert old_domain == "old.example"
    # Reseller channel: only admin A.
    assert reseller_sent_to == [111]


@pytest.mark.database
def test_delete_notifies_with_cleared_pin_addendum(db_session, monkeypatch):
    from app.api.v1.endpoints import super_admin as sa
    from app.models.admin_tld_state import AdminTldState
    from app.models.admins import Admin
    from app.models.registered_tld import RegisteredTld

    _stub_commit(db_session, monkeypatch)

    reseller_msgs = {}
    monkeypatch.setattr(
        "app.services.notifications.send_alert.send_telegram_alert",
        lambda tg_id, msg: (reseller_msgs.setdefault(tg_id, msg) or True),
    )

    class _FakeTask:
        @staticmethod
        def delay(*a, **k):
            return None

    monkeypatch.setattr(
        "app.tasks.end_user_notifications.notify_end_users_tld_changed",
        _FakeTask,
    )

    # Avoid a real DNS-provider call during delete (best-effort path).
    class _FakeDnsClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def find_a_record_by_name(self, name):
            return None

        async def delete_dns_record(self, rid):
            return None

    monkeypatch.setattr(sa, "create_dns_client", lambda **kw: _FakeDnsClient())

    t1 = RegisteredTld(
        domain="old.example",
        dns_provider="cloudflare",
        zone_id="Z",
        purpose="subscription",
        is_active=True,
        server_ip="1.2.3.4",
    )
    t2 = RegisteredTld(
        domain="new.example",
        dns_provider="cloudflare",
        zone_id="Z",
        purpose="subscription",
        is_active=True,
        server_ip="1.2.3.4",
    )
    db_session.add_all([t1, t2])
    db_session.flush()
    a = Admin(username="ra", password_hash="x", status="active", telegram_id="111")
    db_session.add(a)
    db_session.flush()
    db_session.add(
        AdminTldState(
            admin_id=a.id,
            purpose="subscription",
            pinned_tld_id=t1.id,
            effective_tld_id=t1.id,
            source="pin",
        )
    )
    db_session.flush()

    asyncio.run(sa.delete_tld(t1.id, db=db_session, current={"id": 1}))

    assert 111 in reseller_msgs
    assert "pin" in reseller_msgs[111].lower()  # cleared-pin addendum (delete path)
    assert "deleted" in reseller_msgs[111]


# ---------------------------------------------------------------------------
# Task 5 (Phase 3) — wire notifications into pin set/clear
# ---------------------------------------------------------------------------


@pytest.mark.database
def test_pin_change_to_different_tld_notifies(db_session, monkeypatch):
    """Pinning an admin to a TLD different from their current effective fires
    both channels for that admin only."""
    from app.api.v1.endpoints import super_admin as sa
    from app.models.admin_tld_state import AdminTldState
    from app.models.admins import Admin
    from app.models.registered_tld import RegisteredTld
    from app.schemas.super_admin import TldPinRequest

    _stub_commit(db_session, monkeypatch)

    enqueued = []
    reseller_to = []
    monkeypatch.setattr(
        "app.services.notifications.send_alert.send_telegram_alert",
        lambda tg_id, msg: (reseller_to.append(tg_id) or True),
    )

    class _FakeTask:
        @staticmethod
        def delay(admin_ids, purpose, new_domain, old_domain=None):
            enqueued.append((tuple(admin_ids), purpose, new_domain, old_domain))

    monkeypatch.setattr(
        "app.tasks.end_user_notifications.notify_end_users_tld_changed",
        _FakeTask,
    )

    t1 = RegisteredTld(
        domain="a.example",
        dns_provider="cloudflare",
        zone_id="Z",
        purpose="dashboard",
        is_active=True,
        server_ip="1.2.3.4",
    )
    t2 = RegisteredTld(
        domain="b.example",
        dns_provider="cloudflare",
        zone_id="Z",
        purpose="dashboard",
        is_active=True,
        server_ip="1.2.3.4",
    )
    db_session.add_all([t1, t2])
    db_session.flush()
    a = Admin(username="ra", password_hash="x", status="active", telegram_id="111")
    db_session.add(a)
    db_session.flush()
    # admin currently effective on t1 (LB)
    db_session.add(
        AdminTldState(
            admin_id=a.id, purpose="dashboard", effective_tld_id=t1.id, source="lb"
        )
    )
    db_session.flush()

    asyncio.run(
        sa.set_tld_pin(
            TldPinRequest(admin_id=a.id, purpose="dashboard", tld_id=t2.id),
            db=db_session,
            current={"id": 1},
        )
    )

    assert len(enqueued) == 1
    admin_ids_arg, purpose, new_domain, old_domain = enqueued[0]
    assert admin_ids_arg == (a.id,)
    assert purpose == "dashboard"
    assert new_domain == "b.example"
    assert old_domain == "a.example"
    assert reseller_to == [111]


@pytest.mark.database
def test_pin_to_already_effective_tld_does_not_notify(db_session, monkeypatch):
    """Pinning an admin to the TLD they are ALREADY effective on moves nobody —
    no notification fires on either channel."""
    from app.api.v1.endpoints import super_admin as sa
    from app.models.admin_tld_state import AdminTldState
    from app.models.admins import Admin
    from app.models.registered_tld import RegisteredTld
    from app.schemas.super_admin import TldPinRequest

    _stub_commit(db_session, monkeypatch)

    delay_calls = []
    reseller_to = []
    monkeypatch.setattr(
        "app.services.notifications.send_alert.send_telegram_alert",
        lambda tg_id, msg: (reseller_to.append(tg_id) or True),
    )

    class _SpyTask:
        @staticmethod
        def delay(*args, **kwargs):
            delay_calls.append(args)

    monkeypatch.setattr(
        "app.tasks.end_user_notifications.notify_end_users_tld_changed",
        _SpyTask,
    )

    t1 = RegisteredTld(
        domain="a.example",
        dns_provider="cloudflare",
        zone_id="Z",
        purpose="dashboard",
        is_active=True,
        server_ip="1.2.3.4",
    )
    db_session.add(t1)
    db_session.flush()
    a = Admin(username="ra", password_hash="x", status="active", telegram_id="111")
    db_session.add(a)
    db_session.flush()
    db_session.add(
        AdminTldState(
            admin_id=a.id, purpose="dashboard", effective_tld_id=t1.id, source="lb"
        )
    )
    db_session.flush()

    asyncio.run(
        sa.set_tld_pin(
            TldPinRequest(admin_id=a.id, purpose="dashboard", tld_id=t1.id),
            db=db_session,
            current={"id": 1},
        )
    )

    assert delay_calls == []  # end-user channel: effective unchanged
    assert reseller_to == []  # reseller channel: not called either
