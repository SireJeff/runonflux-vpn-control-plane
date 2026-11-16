"""Tests for parse_ssh_fields — extracts host/port/user/pass from ssh:// URI."""
import app.services.credentials.connection_string_service as _mod


def test_parse_ssh_fields_basic():
    uri = "ssh://user1:pass1@host.example.com:2222#frag"
    fields = _mod.parse_ssh_fields(uri)
    assert fields == {
        "host": "host.example.com",
        "port": 2222,
        "username": "user1",
        "password": "pass1",
    }


def test_parse_ssh_fields_url_encoded_password():
    uri = "ssh://alice:p%40ss%21@cache-10.example.com:32442#x"
    fields = _mod.parse_ssh_fields(uri)
    assert fields["password"] == "p@ss!"
    assert fields["username"] == "alice"
    assert fields["host"] == "cache-10.example.com"
    assert fields["port"] == 32442


def test_parse_ssh_fields_default_port_when_missing():
    uri = "ssh://user:pass@host.example.com"
    fields = _mod.parse_ssh_fields(uri)
    assert fields["port"] == 22  # SSH default


def test_parse_ssh_fields_returns_none_for_non_ssh():
    """If given a non-ssh URI, should raise or return None — explicit."""
    import pytest

    with pytest.raises(ValueError):
        _mod.parse_ssh_fields("vless://uuid@host:443")


def test_parse_ssh_fields_roundtrip_with_producer():
    """Parser must read what the producer emits.

    Regression: producer used to emit ?user=X&password=Y query params,
    parser expected userinfo@host — they disagreed and parser returned
    empty credentials for all real URIs.
    """
    from unittest.mock import MagicMock

    user = MagicMock()
    user.display_name = "Test User"
    user.username = "alice"
    cred = {"username": "alice", "password": "p@ss!word"}

    # Call the producer's _format_connection_string for ssh.
    # Real signature: (self, user, protocol, cred, domain, port, country_code)
    # We bypass __init__ (which needs a db Session) by using __new__.
    svc = _mod.ConnectionStringService.__new__(_mod.ConnectionStringService)
    uri = svc._format_connection_string(
        user=user,
        protocol="ssh",
        cred=cred,
        domain="cache-10.example.com",
        port=32442,
        country_code="CH",
    )

    # Verify the URI is in userinfo@host form, not query-param form
    assert (
        "user=" not in uri and "password=" not in uri
    ), f"Producer still using query-param form: {uri}"
    assert (
        "alice:p%40ss%21word@cache-10.example.com" in uri
    ), f"Producer URL-encoding broken: {uri}"

    # Round-trip: parser should extract the original credentials
    fields = _mod.parse_ssh_fields(uri)
    assert fields["username"] == "alice", fields
    assert fields["password"] == "p@ss!word", fields
    assert fields["host"] == "cache-10.example.com"
    assert fields["port"] == 32442


def test_parse_ssh_fields_password_with_special_chars():
    """Passwords with &, #, ?, =, spaces must round-trip correctly."""
    tricky_pw = "p@ss#w0rd?&x=1"
    from unittest.mock import MagicMock

    user = MagicMock()
    user.display_name = "Test"
    user.username = "bob"
    cred = {"username": "bob", "password": tricky_pw}

    svc = _mod.ConnectionStringService.__new__(_mod.ConnectionStringService)
    uri = svc._format_connection_string(
        user=user,
        protocol="ssh",
        cred=cred,
        domain="h.example.com",
        port=22,
        country_code="DE",
    )

    fields = _mod.parse_ssh_fields(uri)
    assert (
        fields["password"] == tricky_pw
    ), f"Special-char password broken: got {fields['password']!r}"
    assert fields["username"] == "bob"
