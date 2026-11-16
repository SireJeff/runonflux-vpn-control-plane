"""GET /super/tlds/assignments (phase 5.4a). DB-backed: returns per-admin
effective+pin per purpose; admins with no AdminTldState row show nulls (LB
default = the "(default)" cell in the matrix).

⚠️ FK-parent gotcha: pinned_tld_id / effective_tld_id are
ForeignKey("registered_tlds.id") and the real fluxvpn_test Postgres ENFORCES
them — so the pinned state row MUST reference a seeded parent RegisteredTld
(plain id=5 with no parent would violate admin_tld_states_*_tld_id_fkey at
flush). A mock db_session would not catch this; only the VM run does.

Run via the VM driver against fluxvpn_test (never the prod fluxvpn db).
"""
import asyncio

import pytest

from app.api.v1.endpoints import super_admin as sa
from app.models.admin_tld_state import AdminTldState
from app.models.admins import Admin
from app.models.registered_tld import RegisteredTld


def _stub_commit(db_session, monkeypatch):
    monkeypatch.setattr(db_session, "commit", db_session.flush)


@pytest.mark.database
def test_get_tld_assignments_reports_pin_and_default(db_session, monkeypatch):
    _stub_commit(db_session, monkeypatch)
    # Parent RegisteredTld — the FK target for the pinned state below.
    tld = RegisteredTld(
        domain="pinned.com", dns_provider="cloudflare", purpose="fdm", is_active=True
    )
    db_session.add(tld)
    db_session.flush()

    pinned = Admin(username="pinned", password_hash="x", status="active")
    default = Admin(username="default", password_hash="x", status="active")
    db_session.add_all([pinned, default])
    db_session.flush()
    db_session.add(
        AdminTldState(
            admin_id=pinned.id,
            purpose="fdm",
            pinned_tld_id=tld.id,
            effective_tld_id=tld.id,
            source="pin",
        )
    )
    db_session.flush()

    resp = asyncio.run(sa.get_tld_assignments(db=db_session, current={"id": 1}))
    by_name = {a.username: a for a in resp.assignments}

    # ordered by username -> default before pinned
    assert [a.username for a in resp.assignments] == ["default", "pinned"]

    assert by_name["pinned"].assignments["fdm"].pinned_tld_id == tld.id
    assert by_name["pinned"].assignments["fdm"].effective_tld_id == tld.id
    assert by_name["pinned"].assignments["fdm"].source == "pin"
    # admin with no state row -> nulls (rides the LB = "(default)")
    assert by_name["default"].assignments["fdm"].pinned_tld_id is None
    assert by_name["default"].assignments["fdm"].effective_tld_id is None
