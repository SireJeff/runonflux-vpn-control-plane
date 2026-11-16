"""
Billing Celery Tasks

Background tasks for:
- Wallet balance monitoring with auto-suspend/reactivate
"""

import logging

from celery import shared_task

from app.core.database import SessionLocal
from app.models.admin_users import AdminUser
from app.models.admins import Admin

logger = logging.getLogger(__name__)


# ============================================================================
# WALLET BALANCE MONITORING
# ============================================================================


@shared_task(name="billing.check_wallet_balances")
def check_wallet_balances():
    """Check all active admins' wallet balances.

    Runs every 15 minutes. Suspends admins with $0 balance.
    Reactivates admins with new funds.
    """
    logger.info("Checking wallet balances for all admins")
    db = SessionLocal()
    try:
        # Find admins with zero/negative balance who are still active
        depleted_admins = (
            db.query(Admin)
            .filter(
                Admin.status == "active",
                Admin.wallet_balance <= 0,
            )
            .all()
        )

        suspended_count = 0
        for admin in depleted_admins:
            # Suspend all end users
            users = (
                db.query(AdminUser)
                .filter(
                    AdminUser.admin_id == admin.id,
                    AdminUser.status == "active",
                )
                .all()
            )

            for user in users:
                user.status = "suspended"

            # Decrement domain load for each suspended user
            from app.services.credentials.connection_string_service import (
                ConnectionStringService,
            )

            css = ConnectionStringService(db)
            for user in users:
                css.decrement_domain_on_user_change(user.id)

            suspended_count += 1
            logger.info(f"Suspended admin {admin.username} (wallet depleted)")

        # Find admins with positive balance who have suspended users
        reactivated_admins = (
            db.query(Admin)
            .filter(
                Admin.status == "active",
                Admin.wallet_balance > 0,
            )
            .all()
        )

        reactivated_count = 0
        for admin in reactivated_admins:
            suspended_users = (
                db.query(AdminUser)
                .filter(
                    AdminUser.admin_id == admin.id,
                    AdminUser.status == "suspended",
                )
                .all()
            )

            if suspended_users:
                for user in suspended_users:
                    user.status = "active"

                reactivated_count += 1
                logger.info(
                    f"Reactivated admin {admin.username}'s users (wallet refilled)"
                )

        db.commit()

        result = {
            "suspended_admins": suspended_count,
            "reactivated_admins": reactivated_count,
        }
        logger.info(f"Wallet balance check completed: {result}")
        return result

    except Exception as e:
        logger.exception(f"Wallet balance check failed: {e}")
        db.rollback()
        return {"error": str(e)}
    finally:
        db.close()
