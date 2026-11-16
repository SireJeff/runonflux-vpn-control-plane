"""Unit tests for admin create_user username resolution (Task 8).

Direct-calls the async create_user endpoint with heavy services mocked and a
mocked DB session, so no real database is required. Verifies:
- the schema now treats username as optional;
- omitting username -> generate_unique_username is called and its result used;
- an explicit username is honored as-is (generator not called).

(Note: placed in tests/unit/ rather than tests/integration/ because the
integration client fixture requires the unprovisioned fluxvpn_test DB, which
fails locally; this direct-call approach runs green with zero DB.)
"""

import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import app.api.v1.endpoints.admin_api as _mod


def _stub_response():
    """Stand-in for _build_user_response with valid-typed attrs (Pydantic-safe)."""
    return SimpleNamespace(
        id=1,
        username="rumi_a1f2",
        display_name=None,
        remark=None,
        status="active",
        traffic_used_gb=0.0,
        traffic_limit_gb=10.0,
        macro_region="eu",
        created_at=datetime(2026, 6, 24),
    )


def _mock_db():
    db = MagicMock()
    # Every .first() returns None -> no existing user (uniqueness OK) and the
    # admin-lookup in the notification block returns None (notification skipped).
    db.query.return_value.filter.return_value.first.return_value = None
    return db


def _run(coro):
    return asyncio.run(coro)


def test_create_user_request_username_is_now_optional():
    from app.schemas.admin_api import CreateUserRequest

    req = CreateUserRequest(macro_region="eu")  # username omitted
    assert req.username is None
    req2 = CreateUserRequest(username="acme_corp", macro_region="eu")
    assert req2.username == "acme_corp"


def test_create_user_without_username_generates_one():
    from app.schemas.admin_api import CreateUserRequest

    request = CreateUserRequest(macro_region="eu")
    db = _mock_db()
    with patch.object(_mod, "CredentialService"), patch.object(
        _mod, "ConnectionStringService"
    ) as CS, patch.object(
        _mod, "_build_user_response", return_value=_stub_response()
    ), patch.object(
        _mod, "generate_unique_username", return_value="rumi_a1f2"
    ) as gen, patch.object(
        _mod, "get_dashboard_base_url", return_value="https://dash.test"
    ):
        CS.return_value.generate_connection_strings.return_value = {}
        _run(_mod.create_user(request=request, db=db, current={"id": 5}))
    gen.assert_called_once_with(db, 5)
    added_user = db.add.call_args_list[0][0][0]  # first db.add is the AdminUser
    assert added_user.username == "rumi_a1f2"


def test_create_user_username_exhaustion_raises_503():
    """When generate_unique_username raises RuntimeError (omitted-username
    branch), create_user re-raises as HTTP 503 instead of an opaque 500."""
    from fastapi import HTTPException

    from app.schemas.admin_api import CreateUserRequest

    request = CreateUserRequest(macro_region="eu")  # username omitted -> else branch
    db = _mock_db()
    with patch.object(_mod, "CredentialService"), patch.object(
        _mod, "ConnectionStringService"
    ), patch.object(_mod, "_build_user_response"), patch.object(
        _mod,
        "generate_unique_username",
        side_effect=RuntimeError("exhausted"),
    ), patch.object(
        _mod, "get_dashboard_base_url", return_value="https://dash.test"
    ):
        with pytest.raises(HTTPException) as exc_info:
            _run(_mod.create_user(request=request, db=db, current={"id": 5}))
    assert exc_info.value.status_code == 503


def test_create_user_with_explicit_username_honors_it():
    from app.schemas.admin_api import CreateUserRequest

    request = CreateUserRequest(username="acme_corp", macro_region="eu")
    db = _mock_db()
    with patch.object(_mod, "CredentialService"), patch.object(
        _mod, "ConnectionStringService"
    ) as CS, patch.object(
        _mod, "_build_user_response", return_value=_stub_response()
    ), patch.object(
        _mod, "generate_unique_username"
    ) as gen, patch.object(
        _mod, "get_dashboard_base_url", return_value="https://dash.test"
    ):
        CS.return_value.generate_connection_strings.return_value = {}
        _run(_mod.create_user(request=request, db=db, current={"id": 5}))
    gen.assert_not_called()
    added_user = db.add.call_args_list[0][0][0]
    assert added_user.username == "acme_corp"
