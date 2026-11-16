"""Phase 4.5: FDM_SYNC_INTERVAL_SECONDS must be >= the floor (fail-fast).

Relies on tests/conftest.py having populated os.environ with the other
required Settings fields (DATABASE_URL, JWT_SECRET_KEY, etc.); each case
overrides only FDM_SYNC_INTERVAL_SECONDS via an explicit kwarg. Mirrors
test_settings_super_admin_password.py's pattern exactly.
"""

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_rejects_interval_below_floor():
    with pytest.raises(ValidationError):
        Settings(FDM_SYNC_INTERVAL_SECONDS=60.0)


def test_accepts_interval_at_floor():
    s = Settings(FDM_SYNC_INTERVAL_SECONDS=300.0)
    assert s.FDM_SYNC_INTERVAL_SECONDS == 300.0


def test_accepts_default_interval():
    s = Settings()
    assert s.FDM_SYNC_INTERVAL_SECONDS == 600.0


def test_accepts_tuned_interval_above_default():
    s = Settings(FDM_SYNC_INTERVAL_SECONDS=900.0)
    assert s.FDM_SYNC_INTERVAL_SECONDS == 900.0
