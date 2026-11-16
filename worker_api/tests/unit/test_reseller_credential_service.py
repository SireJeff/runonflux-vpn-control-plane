"""Unit tests for ResellerCredentialService (Task 9C).

The service itself already existed -- this file adds test coverage.
Tests verify: protocol coverage, idempotency, credential_data shapes per
protocol, and the helper get/delete methods.
"""

from unittest.mock import MagicMock

import pytest

from app.services.credentials.reseller_credential_service import (
    CredentialService,
    PROTOCOLS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user(user_id=10, username="test_user"):
    from app.models.admin_users import AdminUser

    user = AdminUser(id=user_id, username=username)
    return user


def _make_existing_cred(protocol, user_id=10):
    """Build a fake existing UserCredentialV2 row (skipped by generate)."""
    from app.models.user_credentials_v2 import UserCredentialV2

    return UserCredentialV2(
        id=hash(protocol) % 1000,  # stable fake id
        user_id=user_id,
        protocol=protocol,
        credential_data={"existing": True},
    )


# ---------------------------------------------------------------------------
# generate_user_credentials tests
# ---------------------------------------------------------------------------


def test_generate_user_credentials_creates_6_rows_for_new_user():
    """New user gets all 6 protocols generated."""
    user = _make_user(user_id=10, username="alice")
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = None

    added_rows = []
    mock_db.add.side_effect = lambda row: added_rows.append(row)

    service = CredentialService(mock_db)
    result = service.generate_user_credentials(user)

    # Returned dict has all 6 protocols
    assert set(result.keys()) == set(PROTOCOLS)
    # All 6 were added to db
    assert len(added_rows) == 6
    # Each row has correct user_id and unique protocol
    assert all(r.user_id == 10 for r in added_rows)
    assert {r.protocol for r in added_rows} == set(PROTOCOLS)
    # Commit called once at the end
    mock_db.commit.assert_called_once()


def test_generate_user_credentials_skips_existing_protocols():
    """If user already has a cred for a protocol, skip it (no duplicate add)."""
    user = _make_user(user_id=10, username="bob")
    # Simulate: each .first() call returns an existing cred for that protocol
    existing_creds = [_make_existing_cred(p) for p in PROTOCOLS]
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.side_effect = existing_creds

    added_rows = []
    mock_db.add.side_effect = lambda row: added_rows.append(row)

    service = CredentialService(mock_db)
    result = service.generate_user_credentials(user)

    # No new rows added -- all 6 were existing
    assert len(added_rows) == 0
    # Result still has all 6 protocols (from existing)
    assert set(result.keys()) == set(PROTOCOLS)
    # Each result entry is the existing cred (not a new one)
    for protocol, cred in result.items():
        assert cred.credential_data == {"existing": True}
    mock_db.commit.assert_called_once()


def test_generate_user_credentials_partial_existing_creates_only_missing():
    """If user has 3 of 6 protocols, only the 3 missing ones are created."""
    user = _make_user(user_id=10, username="carol")
    # First 3 protocols exist, last 3 don't
    side_effects = [
        _make_existing_cred("ssh"),
        _make_existing_cred("ss"),
        _make_existing_cred("vless"),
        None,  # trojan missing
        None,  # outline missing
        None,  # http_proxy missing
    ]
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.side_effect = side_effects

    added_rows = []
    mock_db.add.side_effect = lambda row: added_rows.append(row)

    service = CredentialService(mock_db)
    result = service.generate_user_credentials(user)

    assert len(added_rows) == 3
    new_protocols = {r.protocol for r in added_rows}
    assert new_protocols == {"trojan", "outline", "http_proxy"}
    assert set(result.keys()) == set(PROTOCOLS)  # 3 existing + 3 new


# ---------------------------------------------------------------------------
# Per-protocol credential_data shape tests
# ---------------------------------------------------------------------------


def test_ssh_credential_data_has_username_and_password():
    user = _make_user(username="dave")
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = None
    added = []
    mock_db.add.side_effect = lambda r: added.append(r)

    CredentialService(mock_db).generate_user_credentials(user)

    ssh_cred = next(r for r in added if r.protocol == "ssh")
    assert ssh_cred.credential_data["username"] == "dave"
    assert "password" in ssh_cred.credential_data
    assert (
        len(ssh_cred.credential_data["password"]) >= 16
    )  # token_urlsafe(12) gives ~16 chars


def test_ss_credential_data_has_method_and_password():
    user = _make_user(username="eve")
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = None
    added = []
    mock_db.add.side_effect = lambda r: added.append(r)

    CredentialService(mock_db).generate_user_credentials(user)

    ss_cred = next(r for r in added if r.protocol == "ss")
    assert ss_cred.credential_data["method"] == "aes-256-gcm"
    assert "password" in ss_cred.credential_data
    assert len(ss_cred.credential_data["password"]) >= 32  # token_urlsafe(32)


def test_vless_credential_data_has_valid_uuid():
    import uuid as uuid_mod

    user = _make_user(username="frank")
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = None
    added = []
    mock_db.add.side_effect = lambda r: added.append(r)

    CredentialService(mock_db).generate_user_credentials(user)

    vless_cred = next(r for r in added if r.protocol == "vless")
    # Must be a valid UUID
    parsed = uuid_mod.UUID(vless_cred.credential_data["uuid"])
    assert str(parsed) == vless_cred.credential_data["uuid"]


def test_trojan_credential_data_has_password():
    user = _make_user(username="grace")
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = None
    added = []
    mock_db.add.side_effect = lambda r: added.append(r)

    CredentialService(mock_db).generate_user_credentials(user)

    trojan_cred = next(r for r in added if r.protocol == "trojan")
    assert "password" in trojan_cred.credential_data
    assert len(trojan_cred.credential_data["password"]) > 0


def test_outline_credential_data_has_access_key_and_method():
    user = _make_user(username="henry")
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = None
    added = []
    mock_db.add.side_effect = lambda r: added.append(r)

    CredentialService(mock_db).generate_user_credentials(user)

    outline_cred = next(r for r in added if r.protocol == "outline")
    assert outline_cred.credential_data["method"] == "chacha20-ietf-poly1305"
    assert outline_cred.credential_data["access_key"].startswith("ss://")
    assert "password" in outline_cred.credential_data


def test_http_proxy_credential_data_has_username_and_password():
    user = _make_user(username="iris")
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = None
    added = []
    mock_db.add.side_effect = lambda r: added.append(r)

    CredentialService(mock_db).generate_user_credentials(user)

    proxy_cred = next(r for r in added if r.protocol == "http_proxy")
    assert proxy_cred.credential_data["username"] == "iris"
    assert "password" in proxy_cred.credential_data


# ---------------------------------------------------------------------------
# get_user_credentials tests
# ---------------------------------------------------------------------------


def test_get_user_credentials_returns_dict_keyed_by_protocol():
    mock_db = MagicMock()
    fake_rows = [_make_existing_cred(p, user_id=10) for p in PROTOCOLS]
    mock_db.query.return_value.filter.return_value.all.return_value = fake_rows

    service = CredentialService(mock_db)
    result = service.get_user_credentials(user_id=10)

    assert set(result.keys()) == set(PROTOCOLS)
    assert all(c.user_id == 10 for c in result.values())


def test_get_user_credentials_empty_for_user_with_no_creds():
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.all.return_value = []

    service = CredentialService(mock_db)
    result = service.get_user_credentials(user_id=999)

    assert result == {}


# ---------------------------------------------------------------------------
# delete_user_credentials tests
# ---------------------------------------------------------------------------


def test_delete_user_credentials_returns_count_and_commits():
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.delete.return_value = 6

    service = CredentialService(mock_db)
    count = service.delete_user_credentials(user_id=10)

    assert count == 6
    mock_db.commit.assert_called_once()


def test_delete_user_credentials_returns_zero_for_user_with_no_creds():
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.delete.return_value = 0

    service = CredentialService(mock_db)
    count = service.delete_user_credentials(user_id=999)

    assert count == 0
    mock_db.commit.assert_called_once()
