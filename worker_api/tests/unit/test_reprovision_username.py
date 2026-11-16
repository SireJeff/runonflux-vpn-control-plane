# worker_api/tests/unit/test_reprovision_username.py
from unittest.mock import MagicMock


def _cred(protocol, data):
    c = MagicMock()
    c.protocol = protocol
    c.credential_data = data
    return c


def _service_with(creds):
    from app.services.credentials.reseller_credential_service import CredentialService

    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = creds
    return CredentialService(db), db


def test_reprovision_rewrites_ssh_and_http_username():
    ssh = _cred("ssh", {"username": "old_u", "password": "keep_ssh"})
    http = _cred("http_proxy", {"username": "old_u", "password": "keep_http"})
    svc, _ = _service_with([ssh, http])
    user = MagicMock(id=1, username="new_u")
    changed = svc.reprovision_username(user)
    assert ssh.credential_data["username"] == "new_u"
    assert ssh.credential_data["password"] == "keep_ssh"  # password preserved
    assert http.credential_data["username"] == "new_u"
    assert http.credential_data["password"] == "keep_http"
    assert set(changed) >= {"ssh", "http_proxy"}


def test_reprovision_recomputes_trojan_password_and_leaves_others():
    trojan = _cred("trojan", {"password": "old_derived"})
    vless = _cred("vless", {"uuid": "u-1"})
    ss = _cred("ss", {"method": "aes-256-gcm", "password": "kept"})
    svc, _ = _service_with([trojan, vless, ss])
    user = MagicMock(id=1, username="new_u")
    changed = svc.reprovision_username(user)
    assert trojan.credential_data["password"] == svc._trojan_password("new_u")
    assert trojan.credential_data["password"] != "old_derived"
    assert vless.credential_data == {"uuid": "u-1"}  # untouched
    assert ss.credential_data == {"method": "aes-256-gcm", "password": "kept"}
    assert "vless" not in changed and "ss" not in changed
    assert "trojan" in changed
