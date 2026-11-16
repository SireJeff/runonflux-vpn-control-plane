"""
Super-admin seeding utility.

Creates the initial super-admin account on first startup if none exists.
Intended to be called from the FastAPI startup event.
"""

import logging

from app.core.auth.password import hash_password
from app.core.config import settings
from app.models.admins import Admin

logger = logging.getLogger(__name__)


def seed_super_admin(db) -> None:
    """Create super admin if none exists.

    Uses :pymod:`app.core.config.settings` to read the configured username
    and password.

    Args:
        db: A SQLAlchemy session (``SessionLocal`` or a FastAPI-injected
            session via ``Depends(get_db)``).
    """
    existing = (
        db.query(Admin).filter(Admin.username == settings.SUPER_ADMIN_USERNAME).first()
    )
    if existing:
        return

    admin = Admin(
        username=settings.SUPER_ADMIN_USERNAME,
        password_hash=hash_password(settings.SUPER_ADMIN_PASSWORD[:72]),
        status="active",
        display_name="Super Admin",
    )
    db.add(admin)
    db.commit()
    logger.info("Seeded super admin: %s", settings.SUPER_ADMIN_USERNAME)
