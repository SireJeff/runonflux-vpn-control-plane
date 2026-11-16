"Telegram auth regressions: backfill legacy handle rows and reject new nonnumeric account identifiers."
import pytest

from app.models.admins import Admin

pytestmark = pytest.mark.integration


def _mk_admin(db, username, telegram_id, status="active", display_name=None):
    admin = Admin(
        username=username,
        password_hash="x",
        display_name=display_name or username,
        telegram_id=telegram_id,
        status=status,
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)
    return admin


# ---------------------------------------------------------------------------
# check-telegram
# ---------------------------------------------------------------------------


def test_numeric_match_wins_without_username(client, db_session):
    _mk_admin(db_session, "num_admin_1", "555001")
    r = client.get("/api/v1/auth/check-telegram?telegram_id=555001")
    assert r.status_code == 200
    body = r.json()
    assert body["found"] is True
    assert body["username"] == "num_admin_1"
    assert body["role"] == "admin"


def test_username_fallback_backfills_numeric_id(client, db_session):
    admin = _mk_admin(db_session, "heal_admin_1", "healhandle1")
    r = client.get(
        "/api/v1/auth/check-telegram?telegram_id=273823001&username=healhandle1"
    )
    assert r.status_code == 200
    assert r.json()["found"] is True
    db_session.expire_all()
    refreshed = db_session.query(Admin).filter(Admin.id == admin.id).first()
    assert refreshed.telegram_id == "273823001"  # backfilled to numeric


def test_username_fallback_is_case_insensitive_and_strips_at(client, db_session):
    admin = _mk_admin(db_session, "heal_admin_2", "HealHandle2")
    r = client.get(
        "/api/v1/auth/check-telegram?telegram_id=273823002&username=%40healhandle2"
    )
    assert r.status_code == 200
    assert r.json()["found"] is True
    db_session.expire_all()
    refreshed = db_session.query(Admin).filter(Admin.id == admin.id).first()
    assert refreshed.telegram_id == "273823002"


def test_username_no_match_returns_not_found_and_leaves_row(client, db_session):
    admin = _mk_admin(db_session, "heal_admin_3", "healhandle3")
    r = client.get(
        "/api/v1/auth/check-telegram?telegram_id=999003&username=someone_else"
    )
    assert r.status_code == 200
    assert r.json()["found"] is False
    db_session.expire_all()
    refreshed = db_session.query(Admin).filter(Admin.id == admin.id).first()
    assert refreshed.telegram_id == "healhandle3"  # untouched


def test_username_fallback_never_rewrites_a_numeric_admin(client, db_session):
    # Stored telegram_id is numeric "770004"; a caller supplying username "770004"
    # must NOT hijack/rewrite it (scoped to non-numeric rows only).
    admin = _mk_admin(db_session, "num_admin_2", "770004")
    r = client.get("/api/v1/auth/check-telegram?telegram_id=888004&username=770004")
    assert r.status_code == 200
    assert r.json()["found"] is False
    db_session.expire_all()
    refreshed = db_session.query(Admin).filter(Admin.id == admin.id).first()
    assert refreshed.telegram_id == "770004"  # unchanged


# ---------------------------------------------------------------------------
# bot-login
# ---------------------------------------------------------------------------


def test_bot_login_username_fallback_issues_token_and_backfills(client, db_session):
    admin = _mk_admin(db_session, "heal_login_1", "loginhandle1")
    r = client.post(
        "/api/v1/auth/bot-login?telegram_id=273823010&username=loginhandle1"
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["access_token"]
    assert body["username"] == "heal_login_1"
    db_session.expire_all()
    refreshed = db_session.query(Admin).filter(Admin.id == admin.id).first()
    assert refreshed.telegram_id == "273823010"


def test_bot_login_no_match_returns_404(client, db_session):
    # Verifies the HTTP_404_NOT_FOUND fix (was status.HTTP_404 -> AttributeError/500).
    r = client.post("/api/v1/auth/bot-login?telegram_id=999011&username=nobody_here")
    assert r.status_code == 404


def test_bot_login_inactive_admin_not_healed_into_login(client, db_session):
    _mk_admin(db_session, "heal_login_2", "loginhandle2", status="pending")
    r = client.post(
        "/api/v1/auth/bot-login?telegram_id=273823012&username=loginhandle2"
    )
    # Row self-heals, but bot-login still rejects non-active admins.
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# register validation (prevent recurrence)
# ---------------------------------------------------------------------------


def test_register_rejects_non_numeric_telegram_id(client, db_session):
    r = client.post(
        "/api/v1/auth/register",
        json={"username": "reg_bad_1", "telegram_id": "fixture-user.invalid"},
    )
    assert r.status_code == 422


def test_register_accepts_numeric_telegram_id(client, db_session):
    r = client.post(
        "/api/v1/auth/register",
        json={"username": "reg_good_1", "telegram_id": "123456789"},
    )
    assert r.status_code == 201, r.text
    row = db_session.query(Admin).filter(Admin.username == "reg_good_1").first()
    assert row is not None
    assert row.telegram_id == "123456789"
