"""End-user usernames must be unique across ALL resellers, case-insensitively.

VPN containers key Xray clients by ``email = username`` across every reseller,
and Xray compares emails case-insensitively. A single collision (e.g. two
resellers each creating ``test2``) makes Xray reject its whole config, which
crash-looped every VLESS/Trojan container in production (2026-10-24).

DB-backed (real Postgres via the ``db_session`` fixture).
"""

import asyncio
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from sqlalchemy import text, update
from sqlalchemy.exc import IntegrityError

import app.api.v1.endpoints.admin_api as admin_api_mod
from app.api.v1.endpoints.internal_v2 import sync_users
from app.models.admin_users import AdminUser
from app.models.admins import Admin
from app.models.user_credentials_v2 import UserCredentialV2
from app.services.credentials import username_generator
from app.services.credentials.username_generator import (
    generate_unique_username,
    username_taken,
)
from app.services.free_config.free_config_service import FreeConfigService
from app.services.subscriptions.adjustment_service import AdjustmentService


def _reseller(db, name):
    adm = Admin(username=name, password_hash="x", status="active")
    db.add(adm)
    db.flush()
    return adm


def _end_user(db, admin, username, status="active"):
    user = AdminUser(admin_id=admin.id, username=username, status=status)
    db.add(user)
    db.flush()
    return user


# --- username_taken ---------------------------------------------------------


def test_username_taken_sees_other_resellers(db_session):
    r1, r2 = _reseller(db_session, "r1"), _reseller(db_session, "r2")
    _end_user(db_session, r1, "test2")
    assert username_taken(db_session, "test2") is True
    assert r2.id != r1.id  # the check is global, not scoped to a reseller


def test_username_taken_is_case_insensitive(db_session):
    r1 = _reseller(db_session, "r1")
    _end_user(db_session, r1, "Alice")
    assert username_taken(db_session, "alice") is True
    assert username_taken(db_session, "ALICE") is True


def test_username_taken_ignores_deleted_users(db_session):
    r1 = _reseller(db_session, "r1")
    _end_user(db_session, r1, "gone", status="deleted")
    assert username_taken(db_session, "gone") is False


def test_username_taken_counts_users_with_null_status(db_session):
    r1 = _reseller(db_session, "r1")
    u = _end_user(db_session, r1, "nullstat")
    # ORM applies the column default for None, so force a real NULL via SQL.
    db_session.execute(
        update(AdminUser).where(AdminUser.id == u.id).values(status=None)
    )
    assert (
        db_session.execute(
            text("SELECT status FROM admin_users WHERE id=:i"),
            {"i": u.id},
        ).scalar()
        is None
    )
    assert username_taken(db_session, "nullstat") is True


def test_username_taken_can_exclude_the_user_being_renamed(db_session):
    r1 = _reseller(db_session, "r1")
    me = _end_user(db_session, r1, "me")
    assert username_taken(db_session, "ME", exclude_user_id=me.id) is False


# --- creation / rename paths -------------------------------------------------


def test_generator_skips_name_held_by_another_reseller(db_session, monkeypatch):
    r1, r2 = _reseller(db_session, "r1"), _reseller(db_session, "r2")
    _end_user(db_session, r1, "rumi_aaaa")
    choices = iter(["rumi", "hafez"])
    monkeypatch.setattr(
        username_generator.secrets, "choice", lambda _seq: next(choices)
    )
    monkeypatch.setattr(username_generator.secrets, "token_hex", lambda _n: "aaaa")
    assert generate_unique_username(db_session, r2.id) == "hafez_aaaa"


def test_set_username_rejects_case_variant_of_another_resellers_user(db_session):
    r1, r2 = _reseller(db_session, "r1"), _reseller(db_session, "r2")
    _end_user(db_session, r1, "test2")
    victim = _end_user(db_session, r2, "someone")
    with pytest.raises(ValueError, match="username_taken"):
        AdjustmentService(db_session).set_username(victim, r2.id, "TEST2")


def test_create_user_rejects_name_held_by_another_reseller(db_session):
    from app.schemas.admin_api import CreateUserRequest

    r1, r2 = _reseller(db_session, "r1"), _reseller(db_session, "r2")
    _end_user(db_session, r1, "test2")
    request = CreateUserRequest(username="Test2", macro_region="eu")
    with patch.object(admin_api_mod, "CredentialService"), pytest.raises(
        HTTPException
    ) as exc:
        asyncio.run(
            admin_api_mod.create_user(
                request=request, db=db_session, current={"id": r2.id}
            )
        )
    assert exc.value.status_code == 409


def test_free_config_users_of_two_resellers_do_not_collide(db_session):
    r1, r2 = _reseller(db_session, "r1"), _reseller(db_session, "r2")
    svc = FreeConfigService(db_session)
    u1 = svc._get_or_create_free_user(r1.id)
    u2 = svc._get_or_create_free_user(r2.id)
    assert u1.username.lower() != u2.username.lower()
    # and it is stable: a second call returns the same row
    assert svc._get_or_create_free_user(r1.id).id == u1.id


# --- database guard -----------------------------------------------------------


def test_db_rejects_case_variant_duplicate_across_resellers(db_session):
    r1, r2 = _reseller(db_session, "r1"), _reseller(db_session, "r2")
    _end_user(db_session, r1, "dup")
    with pytest.raises(IntegrityError):
        _end_user(db_session, r2, "DUP")


def test_db_allows_reusing_a_deleted_users_name(db_session):
    r1, r2 = _reseller(db_session, "r1"), _reseller(db_session, "r2")
    _end_user(db_session, r1, "reuse", status="deleted")
    _end_user(db_session, r2, "reuse")  # must not raise


# --- sync-users never emits a duplicate ---------------------------------------


def test_sync_users_never_emits_case_insensitive_duplicates(db_session):
    """Defence in depth: even if a duplicate slips into the DB (legacy rows,
    manual SQL), one bad row must not crash every container fleet-wide."""
    r1, r2 = _reseller(db_session, "r1"), _reseller(db_session, "r2")
    a = _end_user(db_session, r1, "twin")
    db_session.add(
        UserCredentialV2(
            user_id=a.id, protocol="vless", credential_data={"uuid": "u-1"}
        )
    )
    db_session.flush()
    # Bypass the DB guard the way legacy data would: drop it for this txn only.
    db_session.execute(text("DROP INDEX IF EXISTS uq_admin_users_username_ci"))
    b = _end_user(db_session, r2, "TWIN")
    db_session.add(
        UserCredentialV2(
            user_id=b.id, protocol="vless", credential_data={"uuid": "u-2"}
        )
    )
    db_session.flush()

    resp = sync_users(protocol="vless", db=db_session, _=True)

    names = [u.username.lower() for u in resp.users]
    assert names.count("twin") == 1
    # the oldest row (lowest id) wins, deterministically
    assert [
        u.credential_data["uuid"] for u in resp.users if u.username.lower() == "twin"
    ] == ["u-1"]
