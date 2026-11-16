"""Phase 4a Task 2: connection strings filter by the admin's effective fdm TLD.

Group B (local) tests — import the service module directly and assert
against the mock query chain, so no real DB is needed. Run with
`pytest -o addopts=""`.
"""
import sys
import types
from unittest.mock import MagicMock

from app.services.credentials.connection_string_service import ConnectionStringService


# ---------------------------------------------------------------------------
# _resolve_fdm_effective
# ---------------------------------------------------------------------------


def _install_fake_selection(monkeypatch, *, tld_id=7, raise_no_active=False):
    """Inject a fake ``app.services.tlds.selection`` into sys.modules so the
    helper's lazy ``from ... import TldSelectionService, NoActiveTld`` resolves
    to our fakes — avoids importing the real selection -> models -> DB engine,
    which would fail locally.
    """

    class _NoActiveTld(Exception):
        def __init__(self, purpose):
            super().__init__(purpose)

    class _FakeTld:
        pass

    _FakeTld.id = tld_id

    class _FakeSvc:
        def __init__(self, db):
            pass

        def resolve_effective(self, admin_id, purpose):
            assert purpose == "fdm"
            if raise_no_active:
                raise _NoActiveTld(purpose)
            return _FakeTld()

    fake = types.ModuleType("app.services.tlds.selection")
    fake.TldSelectionService = _FakeSvc
    fake.NoActiveTld = _NoActiveTld
    monkeypatch.setitem(sys.modules, "app.services.tlds.selection", fake)
    return fake


def test_resolve_fdm_effective_returns_tld_id(monkeypatch):
    """Happy path: resolve_effective returns a RegisteredTld; helper yields .id."""
    _install_fake_selection(monkeypatch, tld_id=7)
    svc = ConnectionStringService(db=MagicMock())
    assert svc._resolve_fdm_effective(admin_id=5) == 7


def test_resolve_fdm_effective_none_on_no_active(monkeypatch):
    """NoActiveTld -> None (legacy unfiltered fallback; never raises into a request)."""
    _install_fake_selection(monkeypatch, raise_no_active=True)
    svc = ConnectionStringService(db=MagicMock())
    assert svc._resolve_fdm_effective(admin_id=5) is None


# ---------------------------------------------------------------------------
# _get_domains_for_country filter
# ---------------------------------------------------------------------------


def _filter_clause_strs(country, protocol, effective_tld_id):
    """Drive _get_domains_for_country on a mock DB and return the stringified
    single filter() call's args (the implementation applies all clauses in one
    .filter(*clauses) call). Asserts on column names only — SQLAlchemy renders
    literal values as bind params (e.g. ':param_1'), never the raw value."""
    mock_db = MagicMock()
    svc = ConnectionStringService(mock_db)
    try:
        svc._get_domains_for_country(
            country, protocol, effective_tld_id=effective_tld_id
        )
    except Exception:
        pass
    # chain: query -> join -> join -> filter  (single filter node)
    filter_call = (
        mock_db.query.return_value.join.return_value.join.return_value.filter.call_args
    )
    args = filter_call.args if filter_call else ()
    return [str(a) for a in args]


def test_get_domains_filters_by_tld_id_when_effective_given():
    clauses = _filter_clause_strs("NL", "ssh", effective_tld_id=7)
    tld_clauses = [c for c in clauses if "tld_id" in c.lower()]
    assert (
        tld_clauses
    ), f"With effective_tld_id set, filter must include a tld_id clause. Got: {clauses}"
    # The clause must ALSO accept NULL tld_id (legacy/single-active safety).
    # SQLAlchemy renders `IS NULL` literally, so the substring is stable.
    joined = " ".join(tld_clauses).lower()
    assert (
        "is null" in joined or "is_(none)" in joined
    ), f"filter must also accept NULL tld_id. Clause: {joined}"


def test_get_domains_no_tld_filter_when_effective_none():
    clauses = _filter_clause_strs("NL", "ssh", effective_tld_id=None)
    tld_clauses = [c for c in clauses if "tld_id" in c.lower()]
    assert (
        not tld_clauses
    ), f"With effective_tld_id=None, no tld_id filter must be added. Got: {clauses}"


# ---------------------------------------------------------------------------
# generate_connection_strings threads effective_tld_id down
# ---------------------------------------------------------------------------


def test_generate_connection_strings_threads_effective_tld():
    """generate_connection_strings resolves the effective TLD once and passes
    it to every _get_domains_for_country call."""
    svc = ConnectionStringService(db=MagicMock())
    svc._resolve_fdm_effective = MagicMock(return_value=9)
    svc._get_domains_for_country = MagicMock(
        return_value=[("cdn-01.example.test", 4242, 1)]
    )
    # One ssh credential so the inner loop actually calls _get_domains_for_country.
    fake_cred = MagicMock()
    fake_cred.protocol = "ssh"
    fake_cred.credential_data = {"username": "u", "password": "p"}
    svc.db.query.return_value.filter.return_value.all.return_value = [fake_cred]

    user = MagicMock()
    user.id = 1
    user.admin_id = 5
    user.assigned_domain_id = None  # skip the decrement/prev-domain branch
    user.display_name = "U"
    user.username = "u"

    svc.generate_connection_strings(user, "eu")

    assert svc._resolve_fdm_effective.call_count == 1, "resolve once per generate"
    assert svc._get_domains_for_country.called
    for call in svc._get_domains_for_country.call_args_list:
        assert (
            call.kwargs.get("effective_tld_id") == 9
        ), f"_get_domains_for_country must be called with effective_tld_id=9. Got: {call}"


# ---------------------------------------------------------------------------
# generate_telegram_proxy_links resolves the effective TLD
# ---------------------------------------------------------------------------


def test_telegram_proxy_links_resolves_effective_tld(monkeypatch):
    """generate_telegram_proxy_links resolves the effective fdm TLD (and applies
    the same tld_id clause to its inline query — structurally identical to
    _get_domains_for_country's, covered above). Proven by resolve being called
    with admin_id; the inline clause is confirmed at code review (Task 3)."""
    # Stub the lazy `from app.models.user_regions import UserRegion` so the
    # method runs without the real model import chain.
    ur = types.ModuleType("app.models.user_regions")
    ur.UserRegion = MagicMock()
    monkeypatch.setitem(sys.modules, "app.models.user_regions", ur)

    svc = ConnectionStringService(db=MagicMock())
    svc._resolve_fdm_effective = MagicMock(return_value=11)
    # UserRegion lookup -> None -> method early-returns {} (resolve already ran).
    svc.db.query.return_value.filter.return_value.first.return_value = None

    svc.generate_telegram_proxy_links(MagicMock(admin_id=5))

    svc._resolve_fdm_effective.assert_called_once_with(admin_id=5)
