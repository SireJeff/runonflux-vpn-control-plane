"""Fix 5: SUPER_ADMIN_PASSWORD must be a real secret (fail-fast).

Relies on tests/conftest.py having populated os.environ with the other
required Settings fields (DATABASE_URL, JWT_SECRET_KEY, etc.); each case
overrides only SUPER_ADMIN_PASSWORD via an explicit kwarg.
"""

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_rejects_empty_super_admin_password():
    with pytest.raises(ValidationError):
        Settings(SUPER_ADMIN_PASSWORD="")


def test_rejects_placeholder_super_admin_password():
    with pytest.raises(ValidationError):
        Settings(SUPER_ADMIN_PASSWORD="change_me_in_production")


def test_accepts_real_super_admin_password():
    s = Settings(SUPER_ADMIN_PASSWORD="a-real-secret-value")
    assert s.SUPER_ADMIN_PASSWORD == "a-real-secret-value"
