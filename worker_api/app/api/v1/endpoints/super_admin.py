"""
Super Admin API Endpoints for FluxVPN Reseller Platform

Administrative interface for managing admin resellers, wire transfer orders,
platform settings, and platform-wide analytics.

All endpoints require super_admin role.
"""

import asyncio
import logging
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from app.core.auth.password import hash_password
from app.core.auth.role_dependencies import require_super_admin
from app.core.config import settings
from app.core.database import get_db
from app.models.admin_tld_state import AdminTldState
from app.models.admin_users import AdminUser
from app.models.admins import Admin
from app.models.fdm import FdmDeployment, FdmDomain
from app.models.flux_app_registration import FluxAppRegistration
from app.models.platform_settings import PlatformSetting
from app.models.registered_tld import PURPOSES, RegisteredTld
from app.models.tld_usage_daily import TldUsageDaily
from app.models.traffic_logs import TrafficLog
from app.models.user_credentials_v2 import UserCredentialV2
from app.models.user_regions import UserRegion
from app.models.wallet_transaction_v2 import WalletTransactionV2
from app.models.wire_orders import WireOrder
from app.schemas.super_admin import (
    AdminDetailResponse,
    AdminListResponse,
    AppRegistrationResponse,
    ApproveAdminRequest,
    CreditWalletRequest,
    MigrateTldRequest,
    MigrateTldResponse,
    PendingAdminResponse,
    PlatformAnalytics,
    PlatformSettingsResponse,
    RegisterAppRequest,
    ReviewOrderRequest,
    TldActivateResponse,
    TldAdminAssignment,
    TldAnalyticsSeries,
    TldAnalyticsSeriesDay,
    TldAnalyticsSnapshot,
    TldAnalyticsTld,
    TldAssignmentCell,
    TldAssignmentsResponse,
    TldCreateRequest,
    TldDnsHealth,
    TldListResponse,
    TldPinRequest,
    TldResponse,
    UpdateAppRequest,
    UpdateSettingsRequest,
    WireOrderResponse,
)
from app.services.credentials.connection_string_service import ConnectionStringService
from app.services.fdm.dns_provider import create_dns_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/super", tags=["Super Admin"])


# ============================================================================
# HELPER FUNCTIONS (TLD Management)
# ============================================================================


def _detect_server_ip() -> Optional[str]:
    import httpx

    try:
        with httpx.Client(timeout=5) as client:
            resp = client.get("https://api.ipify.org")
            if resp.status_code == 200:
                return resp.text.strip()
    except Exception:
        pass
    return None


def _upsert_platform_setting(db: Session, key: str, value: str):
    setting = db.query(PlatformSetting).filter(PlatformSetting.key == key).first()
    if setting:
        setting.value = value
    else:
        db.add(PlatformSetting(key=key, value=value))
    db.flush()


async def _broadcast_tld_change(
    purpose: str, old_domain: Optional[str], new_domain: str, db: Session
) -> int:
    from app.models.admins import Admin
    from app.services.notifications.send_alert import send_telegram_alert

    purpose_labels = {
        "fdm": "VPN Connection Domain",
        "subscription": "Subscription Link Domain",
        "dashboard": "Dashboard Domain",
    }
    label = purpose_labels.get(purpose, purpose)

    if purpose == "fdm":
        message = (
            f"{label} Changed\n"
            f"New domain: {new_domain}\n"
            f"Please refresh your subscription link to get updated connections."
        )
    elif purpose == "subscription":
        message = (
            f"{label} Changed\n"
            f"New domain: {new_domain}\n"
            f"Your subscription link has been updated automatically."
        )
    else:
        message = (
            f"{label} Changed\n"
            f"New URL: https://{new_domain}\n"
            f"Please use the new address to access the dashboard."
        )

    admins = (
        db.query(Admin)
        .filter(Admin.status == "active", Admin.telegram_id.isnot(None))
        .all()
    )
    notified = 0
    for admin in admins:
        try:
            telegram_id = admin.telegram_id
            # guaranteed by the telegram_id.isnot(None) filter above
            assert telegram_id is not None
            if send_telegram_alert(int(telegram_id), message):
                notified += 1
        except Exception:
            pass
    return notified


_RESELLER_TLD_PURPOSE_LABELS = {
    "fdm": "VPN connection",
    "subscription": "subscription link",
    "dashboard": "user panel",
    "admin_panel": "admin panel",
}


def _format_reseller_tld_notice(
    purpose_label: str,
    old_domain: Optional[str],
    new_domain: str,
    action: str,
    moved_count: int,
    pin_cleared: bool,
) -> str:
    """English reseller-facing TLD change notice (spec §8 Channel 2)."""
    if action == "updated":
        msg = f"ℹ️ Your {purpose_label} is now `{new_domain}`."
    else:
        msg = (
            f"ℹ️ TLD `{old_domain}` ({purpose_label}) was {action}.\n"
            f"{moved_count} of your active users moved to `{new_domain}`."
        )
    if pin_cleared:
        msg += "\nYour pin to this TLD was removed."
    return msg


def _notify_resellers_tld_change(
    db: Session,
    affected: list,
    cleared: list,
    action: str,
) -> int:
    """Send a TARGETED reseller-bot alert to each affected admin only.

    affected: [(admin_id, purpose, old_domain, new_domain), ...] (from migrate_off).
    cleared:  [(admin_id, purpose), ...] (admins whose pin was cleared on delete).
    action:   'deactivated' | 'deleted' | 'updated'.

    Best-effort: failures are logged, never raised. Returns # admins alerted.
    """
    from sqlalchemy import func

    from app.models.admin_users import AdminUser
    from app.models.admins import Admin
    from app.services.notifications.send_alert import send_telegram_alert

    cleared_set = {(aid, pur) for aid, pur in cleared}

    # Active-user count per affected admin (the "N moved" number).
    admin_ids = list({aid for aid, *_ in affected})
    counts: dict = {}
    if admin_ids:
        rows = (
            db.query(AdminUser.admin_id, func.count(AdminUser.id))
            .filter(AdminUser.admin_id.in_(admin_ids), AdminUser.status == "active")
            .group_by(AdminUser.admin_id)
            .all()
        )
        counts = {aid: c for aid, c in rows}

    alerted = 0
    for admin_id, purpose, old_domain, new_domain in affected:
        admin = db.get(Admin, admin_id)
        if not admin or not admin.telegram_id or admin.status != "active":
            continue
        label = _RESELLER_TLD_PURPOSE_LABELS.get(purpose, purpose)
        msg = _format_reseller_tld_notice(
            label,
            old_domain,
            new_domain,
            action,
            moved_count=counts.get(admin_id, 0),
            pin_cleared=(admin_id, purpose) in cleared_set,
        )
        try:
            if send_telegram_alert(int(admin.telegram_id), msg):
                alerted += 1
        except Exception as e:
            logger.warning(f"Reseller TLD notice failed for admin {admin_id}: {e}")
    return alerted


def _notify_tld_migration(
    db: Session,
    affected: list,
    cleared: list,
    action: str,
) -> None:
    """Fan out both channels after a TLD deactivate/delete migration.

    End-user channel: group `affected` by (purpose, new_domain) — users in a
    group share one message — and enqueue one Celery task per group.
    Reseller channel: targeted alert to each affected admin (delegated to
    _notify_resellers_tld_change). Best-effort; failures are logged.
    """
    groups: dict = {}
    for admin_id, purpose, old_domain, new_domain in affected:
        key = (purpose, new_domain)
        g = groups.setdefault(key, {"admin_ids": [], "old_domain": old_domain})
        g["admin_ids"].append(admin_id)
    try:
        from app.tasks.end_user_notifications import notify_end_users_tld_changed

        for (purpose, new_domain), g in groups.items():
            notify_end_users_tld_changed.delay(
                g["admin_ids"],
                purpose,
                new_domain,
                g["old_domain"],
            )
    except Exception as e:
        logger.warning(f"Failed to enqueue end-user TLD migration notices: {e}")
    try:
        _notify_resellers_tld_change(db, affected, cleared, action)
    except Exception as e:
        logger.warning(f"Reseller TLD migration notice failed: {e}")


def _notify_tld_pin_change(
    db: Session,
    admin_id: int,
    purpose: str,
    old_domain: Optional[str],
    new_domain: Optional[str],
) -> None:
    """Fan out both channels when an admin's effective TLD changed due to a pin
    set/clear. No-op by contract when old == new (no effective movement). The
    pin UI is API-only until Phase 5; wiring this now means notices are correct
    the moment the pin dropdown ships. Best-effort."""
    if old_domain == new_domain:
        return
    try:
        from app.tasks.end_user_notifications import notify_end_users_tld_changed

        notify_end_users_tld_changed.delay([admin_id], purpose, new_domain, old_domain)
    except Exception as e:
        logger.warning(f"Failed to enqueue end-user TLD pin notice: {e}")
    try:
        _notify_resellers_tld_change(
            db,
            [(admin_id, purpose, old_domain, new_domain or "")],
            [],
            "updated",
        )
    except Exception as e:
        logger.warning(f"Reseller TLD pin notice failed: {e}")


def _enqueue_end_user_tld_notice(purpose: str) -> None:
    """Fire-and-forget the end-user fan-out after a TLD activation.

    Lazy-imports the Celery task to avoid coupling endpoint import time to the
    tasks/Celery stack. The TLD change has already been committed by the caller,
    so a failure here is logged, not raised.
    """
    try:
        from app.tasks.end_user_notifications import notify_end_users_tld_changed

        notify_end_users_tld_changed.delay(purpose)
    except Exception as e:
        logger.warning(f"Failed to enqueue end-user TLD notice ({purpose}): {e}")


def _enqueue_fdm_sync() -> bool:
    """Dispatch the RESILIENT Celery FDM sync after an fdm TLD activation.

    Returns True if enqueued. This must run on the WORKER (acks_late + retries),
    not as a bare ``asyncio.create_task`` on the API request's event loop: that
    coroutine is never awaited or retained, so it is routinely garbage-collected
    before it runs — and its exceptions are swallowed — leaving the freshly
    activated fdm TLD with 0 FdmDomain rows and no DNS (dark) until the next
    beat cycle. That timing/lost-task window is a direct cause of "reassignment
    sticks but the domain doesn't work" on the fdm side. See audit 2026-08-19.
    Lazy-imports the task to keep endpoint import time off the Celery stack,
    matching _enqueue_end_user_tld_notice.
    """
    try:
        from app.tasks.fdm_tasks import sync_all_deployments

        sync_all_deployments.delay()
        return True
    except Exception as e:
        logger.error(f"Failed to enqueue FDM sync after activation: {e}")
        return False


async def _activate_fdm_tld(db: Session, new_tld, old_tld) -> Dict[str, Any]:
    """Multi-active: ADD new_tld to the fdm pool. Marks it active and triggers
    FDM sync, which (post-4b.1) generates FdmDomain rows for this TLD across all
    deployments + per-subdomain DNS. Does NOT flip siblings, does NOT wipe
    FdmDomain rows, does NOT rewrite FdmDeployment.base_domain. ``old_tld`` is
    accepted for signature parity with the dispatcher (unused), matching
    _activate_subscription_tld. No end-user notice (activate-add moves nobody);
    operator alert via _broadcast_tld_change (spec §7)."""
    details: Dict[str, Any] = {"sync_triggered": False}

    # Commit (not just flush): the activate_tld dispatcher does NOT commit after
    # this helper returns, so the is_active flip must be persisted here -- same
    # contract as the subscription/dashboard/admin_panel siblings.
    new_tld.is_active = True
    db.commit()

    details["sync_triggered"] = _enqueue_fdm_sync()

    await _broadcast_tld_change("fdm", None, new_tld.domain, db)
    return details


async def _activate_http_tld(
    db: Session, new_tld, purpose: str
) -> Dict[str, Any]:
    """Shared activation for the HTTP-served purposes (subscription, dashboard,
    admin_panel).

    Provisions the host end-to-end so it actually works after assignment:
      1. create/refresh the root A-record (DNS -> this server), then
      2. register the dynamic Traefik router + TLS (proxy_routes) so the host is
         reachable over HTTPS — DNS alone is NOT enough; without a Traefik router
         and cert the URL 404s / cert-fails, which was the infra half of the
         "reassignment sticks but the domain doesn't work" audit (2026-08-19),
    then mark active. Multi-active: no sibling flip, no platform_settings
    (url_resolver resolves per-admin effective now)."""
    from app.services.tlds.proxy_routes import register_route

    details: Dict[str, Any] = {
        "dns_record_created": False,
        "proxy_route_registered": False,
    }

    server_ip = new_tld.server_ip or _detect_server_ip()
    if not server_ip:
        raise HTTPException(
            status_code=500, detail="Cannot detect server IP for DNS record"
        )

    try:
        new_client = create_dns_client(
            provider=new_tld.dns_provider,
            domain=new_tld.domain,
            zone_id=new_tld.zone_id,
        )
        async with new_client:
            await new_client.ensure_record_exists(
                name=new_tld.domain, ip=server_ip, ttl=120
            )
            details["dns_record_created"] = True
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to create DNS record: {str(e)}"
        )

    # Fail-open: a missing/unmounted dynamic dir logs + returns False, never
    # blocks activation.
    details["proxy_route_registered"] = register_route(new_tld.domain, purpose)

    new_tld.is_active = True
    db.commit()
    return details


async def _activate_subscription_tld(db: Session, new_tld, old_tld) -> Dict[str, Any]:
    """Multi-active: ADD new_tld to the subscription pool. ``old_tld`` is
    accepted for dispatcher signature parity but unused."""
    return await _activate_http_tld(db, new_tld, "subscription")


async def _activate_dashboard_tld(db: Session, new_tld, old_tld) -> Dict[str, Any]:
    """Multi-active: ADD new_tld to the dashboard pool."""
    return await _activate_http_tld(db, new_tld, "dashboard")


async def _activate_admin_panel_tld(db: Session, new_tld, old_tld) -> Dict[str, Any]:
    """Multi-active: ADD new_tld to the admin-panel (reseller dashboard) pool."""
    return await _activate_http_tld(db, new_tld, "admin_panel")


def _count_active_tlds(db: Session, purpose: str) -> int:
    """Number of active (non-soft-deleted) TLDs for a purpose — the basis for the
    last-active guard in deactivate/delete (refuse to drain the only active TLD)."""
    return (
        db.query(RegisteredTld)
        .filter(
            RegisteredTld.purpose == purpose,
            RegisteredTld.is_active.is_(True),
            RegisteredTld.deleted_at.is_(None),
        )
        .count()
    )


# ============================================================================
# ADMIN MANAGEMENT
# ============================================================================


@router.get("/admins")
async def list_admins(
    status_filter: str | None = Query(None, alias="status"),
    search: str | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current: dict = Depends(require_super_admin),
):
    """
    List all admin resellers with pagination, status filter, and search.

    Returns paginated list with user_count for each admin.
    """
    # Base query with user count subquery
    user_count_sq = (
        db.query(
            AdminUser.admin_id,
            func.count(AdminUser.id).label("user_count"),
        )
        .group_by(AdminUser.admin_id)
        .subquery()
    )

    query = db.query(
        Admin,
        func.coalesce(user_count_sq.c.user_count, 0).label("user_count"),
    ).outerjoin(user_count_sq, Admin.id == user_count_sq.c.admin_id)

    # Apply filters
    if status_filter:
        query = query.filter(Admin.status == status_filter)
    if search:
        pattern = f"%{search}%"
        query = query.filter(
            (Admin.username.ilike(pattern))
            | (Admin.display_name.ilike(pattern))
            | (Admin.telegram_id.ilike(pattern))
        )

    # Count total before pagination
    total = query.count()

    # Paginate
    admins = (
        query.order_by(desc(Admin.created_at))
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    items = [
        AdminListResponse(
            id=admin.id,
            username=admin.username,
            display_name=admin.display_name,
            telegram_id=admin.telegram_id,
            wallet_balance=float(admin.wallet_balance or Decimal("0.00")),
            status=admin.status,
            created_at=admin.created_at,
            user_count=user_count,
        )
        for admin, user_count in admins
    ]

    return {
        "items": [item.model_dump() for item in items],
        "total": total,
        "page": page,
        "per_page": per_page,
    }


@router.get("/admins/pending")
async def list_pending_admins(
    db: Session = Depends(get_db),
    current: dict = Depends(require_super_admin),
):
    """List all pending admin registrations awaiting approval."""
    admins = (
        db.query(Admin)
        .filter(Admin.status == "pending")
        .order_by(Admin.created_at.desc())
        .all()
    )
    return admins


@router.get("/admins/{admin_id}")
async def get_admin_detail(
    admin_id: int,
    db: Session = Depends(get_db),
    current: dict = Depends(require_super_admin),
):
    """
    Get detailed information for a specific admin reseller.

    Includes wallet balance, user count, and recent wallet transactions.
    """
    admin = db.query(Admin).filter(Admin.id == admin_id).first()
    if not admin:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Admin {admin_id} not found",
        )

    # User count
    user_count = db.query(AdminUser).filter(AdminUser.admin_id == admin_id).count()

    # Recent wallet transactions (last 10)
    recent_txns = (
        db.query(WalletTransactionV2)
        .filter(WalletTransactionV2.admin_id == admin_id)
        .order_by(desc(WalletTransactionV2.created_at))
        .limit(10)
        .all()
    )

    recent_transactions = [
        {
            "id": txn.id,
            "amount_usd": float(txn.amount_usd),
            "transaction_type": txn.transaction_type,
            "status": txn.status,
            "description": txn.description,
            "created_at": txn.created_at.isoformat() if txn.created_at else None,
        }
        for txn in recent_txns
    ]

    return AdminDetailResponse(
        id=admin.id,
        username=admin.username,
        display_name=admin.display_name,
        telegram_id=admin.telegram_id,
        whatsapp_number=admin.whatsapp_number,
        phone_number=admin.phone_number,
        wallet_balance=float(admin.wallet_balance or Decimal("0.00")),
        status=admin.status,
        notes=admin.notes,
        approved_by=admin.approved_by,
        approved_at=admin.approved_at,
        created_at=admin.created_at,
        user_count=user_count,
        broadcasts_enabled=admin.broadcasts_enabled,
        recent_transactions=recent_transactions,
    )


@router.post(
    "/admins/{admin_id}/approve",
    status_code=status.HTTP_201_CREATED,
)
async def approve_admin(
    admin_id: int,
    request: ApproveAdminRequest,
    db: Session = Depends(get_db),
    current: dict = Depends(require_super_admin),
):
    """
    Approve a pending admin reseller.

    Sets the provided password, changes status to 'active', and records
    approval metadata. Returns the assigned plaintext password so the
    super admin can deliver it to the reseller.
    """
    admin = db.query(Admin).filter(Admin.id == admin_id).first()
    if not admin:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Admin {admin_id} not found",
        )

    if admin.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Admin status is '{admin.status}', only 'pending' admins can be approved",
        )

    super_admin_id: int = current["id"]

    # Hash password and store both plain text (for delivery) and hash
    admin.password_hash = hash_password(request.password)
    admin.assigned_password = request.password
    admin.status = "active"
    admin.approved_by = super_admin_id
    admin.approved_at = datetime.now(timezone.utc).replace(tzinfo=None)

    db.commit()
    db.refresh(admin)

    # Seed the reseller's starter catalog on first activation (idempotent: no-op
    # if they somehow already have packages).
    from app.services.subscriptions.package_seeder import seed_default_packages

    seed_default_packages(db, admin.id)
    db.commit()

    logger.info(
        f"Super admin {super_admin_id} approved admin {admin_id} ({admin.username})"
    )

    # --- Notify approved admin ---
    try:
        if admin.telegram_id and str(admin.telegram_id).isdigit():
            from app.core.config import settings as app_settings
            from app.services.notifications.send_alert import send_telegram_alert
            from app.services.notifications.templates import (
                format_registration_approved,
            )

            dashboard_url = getattr(
                app_settings, "ADMIN_DASHBOARD_URL", "https://admin.operator7.example.invalid"
            )
            msg = format_registration_approved(
                username=admin.username,
                password=request.password,
                dashboard_url=dashboard_url,
            )
            send_telegram_alert(int(admin.telegram_id), msg)
    except Exception as e:
        logger.warning(f"Failed to send approval notification: {e}")

    return {
        "success": True,
        "message": f"Admin {admin.username} approved successfully",
        "admin_id": admin.id,
        "username": admin.username,
        "assigned_password": admin.assigned_password,
    }


@router.post("/admins/{admin_id}/suspend")
async def suspend_admin(
    admin_id: int,
    db: Session = Depends(get_db),
    current: dict = Depends(require_super_admin),
):
    """
    Suspend an admin reseller and all their end users.

    Sets admin status to 'suspended' and cascades suspension to all admin_users.
    """
    admin = db.query(Admin).filter(Admin.id == admin_id).first()
    if not admin:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Admin {admin_id} not found",
        )

    if admin.status == "suspended":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Admin is already suspended",
        )

    super_admin_id: int = current["id"]
    admin.status = "suspended"

    # Decrement domain load for each active user before suspending
    active_users = (
        db.query(AdminUser)
        .filter(
            AdminUser.admin_id == admin_id,
            AdminUser.status == "active",
        )
        .all()
    )
    css = ConnectionStringService(db)
    for user in active_users:
        css.decrement_domain_on_user_change(user.id)

    # Suspend all end users belonging to this admin
    db.query(AdminUser).filter(AdminUser.admin_id == admin_id).update(
        {"status": "suspended"}, synchronize_session="fetch"
    )

    db.commit()

    logger.info(
        f"Super admin {super_admin_id} suspended admin {admin_id} ({admin.username})"
    )

    return {
        "success": True,
        "message": f"Admin {admin.username} and all their users suspended",
        "admin_id": admin.id,
    }


@router.post("/admins/{admin_id}/activate")
async def activate_admin(
    admin_id: int,
    db: Session = Depends(get_db),
    current: dict = Depends(require_super_admin),
):
    """
    Reactivate a suspended admin reseller and their end users.

    Sets admin status to 'active' and reactivates all admin_users that
    were previously suspended.
    """
    admin = db.query(Admin).filter(Admin.id == admin_id).first()
    if not admin:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Admin {admin_id} not found",
        )

    if admin.status == "active":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Admin is already active",
        )

    super_admin_id: int = current["id"]
    admin.status = "active"

    # Reactivate suspended end users belonging to this admin
    db.query(AdminUser).filter(
        AdminUser.admin_id == admin_id,
        AdminUser.status == "suspended",
    ).update({"status": "active"}, synchronize_session="fetch")

    db.commit()

    logger.info(
        f"Super admin {super_admin_id} activated admin {admin_id} ({admin.username})"
    )

    return {
        "success": True,
        "message": f"Admin {admin.username} and their users reactivated",
        "admin_id": admin.id,
    }


@router.delete("/admins/{admin_id}")
async def hard_delete_admin(
    admin_id: int,
    db: Session = Depends(get_db),
    current: dict = Depends(require_super_admin),
):
    """
    Hard-delete an admin reseller and ALL their end users with related data.

    Deletes in order: traffic_logs → admin_users (cascades to credentials/regions)
    → wallet_transactions → wire_orders → admin row.
    """
    admin = db.query(Admin).filter(Admin.id == admin_id).first()
    if not admin:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Admin {admin_id} not found"
        )

    super_admin_id: int = current["id"]

    # Collect user IDs
    user_ids = [
        uid
        for (uid,) in db.query(AdminUser.id)
        .filter(AdminUser.admin_id == admin_id)
        .all()
    ]

    # Decrement domain load for each user before deletion
    css = ConnectionStringService(db)
    for uid in user_ids:
        css.decrement_domain_on_user_change(uid)

    # Delete traffic logs first (no FK cascade)
    traffic_count = 0
    if user_ids:
        traffic_count = (
            db.query(TrafficLog)
            .filter(TrafficLog.user_id.in_(user_ids))
            .delete(synchronize_session=False)
        )

    # Delete end users (cascades to user_credentials_v2, user_regions)
    user_count = (
        db.query(AdminUser)
        .filter(AdminUser.admin_id == admin_id)
        .delete(synchronize_session=False)
    )

    # Delete wallet transactions
    txn_count = (
        db.query(WalletTransactionV2)
        .filter(WalletTransactionV2.admin_id == admin_id)
        .delete(synchronize_session=False)
    )

    # Delete wire orders
    order_count = (
        db.query(WireOrder)
        .filter(WireOrder.admin_id == admin_id)
        .delete(synchronize_session=False)
    )

    # Delete the admin row
    db.delete(admin)
    db.commit()

    logger.info(
        f"Super admin {super_admin_id} HARD-DELETED admin {admin_id} ({admin.username}): "
        f"{user_count} users, {traffic_count} traffic logs, {txn_count} transactions, {order_count} orders"
    )

    return {
        "success": True,
        "message": f"Admin '{admin.username}' permanently deleted",
        "deleted": {
            "admin_id": admin_id,
            "username": admin.username,
            "end_users": user_count,
            "traffic_logs": traffic_count,
            "wallet_transactions": txn_count,
            "wire_orders": order_count,
        },
    }


@router.delete("/admins/{admin_id}/users/{user_id}")
async def hard_delete_end_user(
    admin_id: int,
    user_id: int,
    db: Session = Depends(get_db),
    current: dict = Depends(require_super_admin),
):
    """
    Hard-delete a single end user and all their related data.

    Deletes: traffic_logs → user (cascades to credentials, region).
    """
    user = (
        db.query(AdminUser)
        .filter(AdminUser.id == user_id, AdminUser.admin_id == admin_id)
        .first()
    )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {user_id} not found under admin {admin_id}",
        )

    super_admin_id: int = current["id"]

    # Decrement domain load before deletion
    css = ConnectionStringService(db)
    css.decrement_domain_on_user_change(user_id)

    # Delete traffic logs first (no FK cascade)
    traffic_count = (
        db.query(TrafficLog)
        .filter(TrafficLog.user_id == user_id)
        .delete(synchronize_session=False)
    )

    # Delete user (cascades to user_credentials_v2, user_regions)
    db.delete(user)
    db.commit()

    logger.info(
        f"Super admin {super_admin_id} HARD-DELETED end user {user_id} ({user.username}) "
        f"from admin {admin_id}: {traffic_count} traffic logs"
    )

    return {
        "success": True,
        "message": f"User '{user.username}' permanently deleted",
        "deleted": {
            "user_id": user_id,
            "username": user.username,
            "admin_id": admin_id,
            "traffic_logs": traffic_count,
        },
    }


@router.post("/admins/{admin_id}/credit")
async def credit_wallet(
    admin_id: int,
    request: CreditWalletRequest,
    db: Session = Depends(get_db),
    current: dict = Depends(require_super_admin),
):
    """
    Credit an admin reseller's wallet.

    Adds the specified USD amount to the admin's wallet balance and
    creates a WalletTransactionV2 record with type 'credit_manual'.
    """
    admin = db.query(Admin).filter(Admin.id == admin_id).first()
    if not admin:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Admin {admin_id} not found",
        )

    if admin.status != "active":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot credit wallet: admin status is '{admin.status}'",
        )

    super_admin_id: int = current["id"]
    amount = request.amount_usd

    balance_before = admin.wallet_balance or Decimal("0.00")
    balance_after = balance_before + amount

    admin.wallet_balance = balance_after

    # Create wallet transaction record for sub-admin
    txn = WalletTransactionV2(
        admin_id=admin_id,
        amount_usd=amount,
        transaction_type="credit_manual",
        status="completed",
        description=f"Manual credit by super_admin #{super_admin_id}: {request.reason}",
        balance_before=balance_before,
        balance_after=balance_after,
    )
    db.add(txn)

    # Mirror as income on super admin's wallet
    sa = db.query(Admin).filter(Admin.id == super_admin_id).first()
    if sa:
        sa_before = sa.wallet_balance or Decimal("0.00")
        sa_after = sa_before + amount
        sa.wallet_balance = sa_after
        sa_txn = WalletTransactionV2(
            admin_id=super_admin_id,
            amount_usd=amount,
            transaction_type="income_credit",
            status="completed",
            description=f"Credit to {admin.username} (admin#{admin_id}): {request.reason}",
            balance_before=sa_before,
            balance_after=sa_after,
        )
        db.add(sa_txn)

    db.commit()
    db.refresh(txn)

    logger.info(
        f"Super admin {super_admin_id} credited ${amount} to admin {admin_id} ({admin.username})"
    )

    return {
        "success": True,
        "message": f"Wallet credited: ${float(amount):.2f}",
        "admin_id": admin.id,
        "amount_usd": float(amount),
        "new_balance": float(balance_after),
        "transaction_id": txn.id,
    }


# ============================================================================
# WIRE ORDER MANAGEMENT
# ============================================================================


@router.get("/orders")
async def list_wire_orders(
    status_filter: str | None = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current: dict = Depends(require_super_admin),
):
    """
    List wire transfer orders with pagination and status filter.

    Joins with admins table to include admin_username.
    """
    query = db.query(WireOrder, Admin.username).outerjoin(
        Admin, WireOrder.admin_id == Admin.id
    )

    if status_filter:
        query = query.filter(WireOrder.status == status_filter)

    total = query.count()

    orders = (
        query.order_by(desc(WireOrder.created_at))
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    items = [
        WireOrderResponse(
            id=order.id,
            admin_id=order.admin_id,
            admin_username=admin_username,
            amount_tomans=float(order.amount_tomans),
            amount_usd=float(order.amount_usd) if order.amount_usd else None,
            payment_method=order.payment_method,
            crypto_txid=order.crypto_txid,
            crypto_link=order.crypto_link,
            contact_telegram=order.contact_telegram,
            contact_whatsapp=order.contact_whatsapp,
            contact_phone=order.contact_phone,
            notes=order.notes,
            status=order.status,
            admin_notes=order.admin_notes,
            reviewed_by=order.reviewed_by,
            reviewed_at=order.reviewed_at,
            created_at=order.created_at,
        )
        for order, admin_username in orders
    ]

    return {
        "items": [item.model_dump() for item in items],
        "total": total,
        "page": page,
        "per_page": per_page,
    }


@router.post("/orders/{order_id}/approve")
async def approve_wire_order(
    order_id: int,
    request: ReviewOrderRequest,
    db: Session = Depends(get_db),
    current: dict = Depends(require_super_admin),
):
    """
    Approve a pending wire transfer order.

    Calculates USD amount from tomans using the provided exchange rate,
    credits the admin's wallet, creates a wallet transaction, and
    updates the order status.
    """
    order = db.query(WireOrder).filter(WireOrder.id == order_id).first()
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order {order_id} not found",
        )

    if order.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Order status is '{order.status}', only 'pending' orders can be approved",
        )

    super_admin_id: int = current["id"]

    if order.payment_method == "crypto":
        # USD was snapshotted at submission; credit it directly (no rate step).
        if order.amount_usd is None or order.amount_usd <= 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Crypto order is missing its USD amount",
            )
        amount_usd = order.amount_usd.quantize(Decimal("0.01"))
    else:
        if not request.exchange_rate or request.exchange_rate <= 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="exchange_rate is required and must be greater than 0",
            )
        from app.services.billing.conversion import tomans_to_usd

        amount_usd = tomans_to_usd(order.amount_tomans, request.exchange_rate)

    # Credit admin wallet
    admin = db.query(Admin).filter(Admin.id == order.admin_id).first()
    if not admin:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Admin {order.admin_id} not found",
        )

    balance_before = admin.wallet_balance or Decimal("0.00")
    balance_after = balance_before + amount_usd
    admin.wallet_balance = balance_after

    # Create wallet transaction for sub-admin
    txn = WalletTransactionV2(
        admin_id=admin.id,
        amount_usd=amount_usd,
        transaction_type="credit_wire",
        status="completed",
        description=(
            f"Wire order #{order_id} approved: {order.amount_tomans} toman at rate {request.exchange_rate}"
            if order.payment_method == "wire"
            else f"Crypto order #{order_id} approved: ${amount_usd} (txid {order.crypto_txid})"
        ),
        reference_id=f"wire_order_{order_id}",
        balance_before=balance_before,
        balance_after=balance_after,
    )
    db.add(txn)

    # Mirror as income on super admin's wallet
    sa = db.query(Admin).filter(Admin.id == super_admin_id).first()
    if sa:
        sa_before = sa.wallet_balance or Decimal("0.00")
        sa_after = sa_before + amount_usd
        sa.wallet_balance = sa_after
        sa_txn = WalletTransactionV2(
            admin_id=super_admin_id,
            amount_usd=amount_usd,
            transaction_type="income_wire",
            status="completed",
            description=f"Wire order #{order_id} from {admin.username}: {order.amount_tomans} toman -> ${amount_usd}",
            reference_id=f"wire_order_{order_id}",
            balance_before=sa_before,
            balance_after=sa_after,
        )
        db.add(sa_txn)

    # Update order
    order.amount_usd = amount_usd
    order.status = "approved"
    order.admin_notes = request.admin_notes
    order.reviewed_by = super_admin_id
    order.reviewed_at = datetime.now(timezone.utc).replace(tzinfo=None)

    db.commit()

    if order.payment_method == "crypto":
        logger.info(
            f"Super admin {super_admin_id} approved crypto order {order_id}: "
            f"${amount_usd} (txid {order.crypto_txid})"
        )
    else:
        logger.info(
            f"Super admin {super_admin_id} approved wire order {order_id}: "
            f"{order.amount_tomans} tomans -> ${amount_usd} at rate {request.exchange_rate}"
        )

    # --- Notify admin about wire order approval ---
    try:
        if admin.telegram_id and str(admin.telegram_id).isdigit():
            from app.services.notifications.send_alert import send_telegram_alert
            from app.services.notifications.templates import format_wire_order_approved

            msg = format_wire_order_approved(
                amount_usd=float(amount_usd),
                new_balance=float(admin.wallet_balance),
            )
            send_telegram_alert(int(admin.telegram_id), msg)
    except Exception as e:
        logger.warning(f"Failed to send wire order approval notification: {e}")

    return {
        "success": True,
        "message": "Wire order approved",
        "order_id": order.id,
        "amount_tomans": float(order.amount_tomans),
        "amount_usd": float(amount_usd),
        "exchange_rate": float(request.exchange_rate)
        if request.exchange_rate
        else None,
    }


@router.post("/orders/{order_id}/reject")
async def reject_wire_order(
    order_id: int,
    request: ReviewOrderRequest,
    db: Session = Depends(get_db),
    current: dict = Depends(require_super_admin),
):
    """
    Reject a pending wire transfer order.

    Updates the order status to 'rejected' and records rejection notes
    and reviewer information.
    """
    order = db.query(WireOrder).filter(WireOrder.id == order_id).first()
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order {order_id} not found",
        )

    if order.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Order status is '{order.status}', only 'pending' orders can be rejected",
        )

    super_admin_id: int = current["id"]

    order.status = "rejected"
    order.admin_notes = request.admin_notes
    order.reviewed_by = super_admin_id
    order.reviewed_at = datetime.now(timezone.utc).replace(tzinfo=None)

    db.commit()

    logger.info(f"Super admin {super_admin_id} rejected wire order {order_id}")

    # --- Notify admin about wire order rejection ---
    try:
        order_admin = db.query(Admin).filter(Admin.id == order.admin_id).first()
        if (
            order_admin
            and order_admin.telegram_id
            and str(order_admin.telegram_id).isdigit()
        ):
            from app.services.notifications.send_alert import send_telegram_alert
            from app.services.notifications.templates import format_wire_order_rejected

            msg = format_wire_order_rejected(reason=request.admin_notes)
            send_telegram_alert(int(order_admin.telegram_id), msg)
    except Exception as e:
        logger.warning(f"Failed to send wire order rejection notification: {e}")

    return {
        "success": True,
        "message": "Wire order rejected",
        "order_id": order.id,
    }


# ============================================================================
# PLATFORM ANALYTICS
# ============================================================================


@router.get("/analytics")
async def get_platform_analytics(
    db: Session = Depends(get_db),
    current: dict = Depends(require_super_admin),
):
    """
    Get platform-wide analytics summary.

    Returns counts for admins (by status), end users (by status),
    total revenue, total traffic (GB), and pending wire orders.
    """
    # Admin counts
    total_admins = db.query(Admin).count()
    active_admins = db.query(Admin).filter(Admin.status == "active").count()
    pending_admins = db.query(Admin).filter(Admin.status == "pending").count()

    # End user counts
    total_end_users = db.query(AdminUser).count()
    active_end_users = db.query(AdminUser).filter(AdminUser.status == "active").count()

    # Total revenue (sum of all admin wallet balances)
    revenue_result = db.query(func.sum(Admin.wallet_balance)).scalar()
    total_revenue_usd = float(revenue_result) if revenue_result else 0.0

    # Total traffic (convert bytes to GB)
    traffic_result = db.query(
        func.sum(TrafficLog.bytes_in) + func.sum(TrafficLog.bytes_out)
    ).scalar()
    total_traffic_gb = float(traffic_result) / (1024**3) if traffic_result else 0.0

    # Pending wire orders
    pending_wire_orders = (
        db.query(WireOrder).filter(WireOrder.status == "pending").count()
    )

    return PlatformAnalytics(
        total_admins=total_admins,
        active_admins=active_admins,
        pending_admins=pending_admins,
        total_end_users=total_end_users,
        active_end_users=active_end_users,
        total_revenue_usd=total_revenue_usd,
        total_traffic_gb=round(total_traffic_gb, 2),
        total_wire_orders_pending=pending_wire_orders,
    )


# ============================================================================
# FLUX APP REGISTRATION
# ============================================================================


def _compute_app_health(
    db: Session, app: FluxAppRegistration
) -> Tuple[List[str], int, bool]:
    """Regions, healthy-active-domain count, and serving flag for one app.

    Phase 4.7a: shared by list_apps and get_app, which previously duplicated
    this block verbatim.
    """
    deployments = (
        db.query(FdmDeployment)
        .filter(FdmDeployment.flux_app_name == app.app_name)
        .all()
    )
    regions = sorted(
        set(d.region.upper() for d in deployments if d.region and d.region != "XX")
    )
    healthy_active = (
        db.query(FdmDomain)
        .join(FdmDeployment)
        .filter(
            FdmDeployment.flux_app_name == app.app_name,
            FdmDeployment.is_active == True,
            FdmDomain.health_status == "healthy",
        )
        .count()
    )
    serving = bool(app.is_active and healthy_active > 0)
    return regions, healthy_active, serving


@router.get("/apps")
async def list_apps(
    db: Session = Depends(get_db),
    current: dict = Depends(require_super_admin),
):
    """List all registered Flux apps with region and health summary."""
    apps = (
        db.query(FluxAppRegistration)
        .order_by(FluxAppRegistration.created_at.desc())
        .all()
    )

    result = []
    for app in apps:
        regions, healthy_active, serving = _compute_app_health(db, app)

        result.append(
            AppRegistrationResponse(
                id=app.id,
                app_name=app.app_name,
                protocol_ports=app.protocol_ports or {},
                is_active=app.is_active,
                registered_by=app.registered_by,
                last_discovery_at=app.last_discovery_at,
                last_discovery_ips=app.last_discovery_ips,
                created_at=app.created_at,
                updated_at=app.updated_at,
                regions=regions,
                healthy_instances=healthy_active,
                serving=serving,
            )
        )

    return result


@router.post("/apps", status_code=status.HTTP_201_CREATED)
async def register_app(
    request: RegisterAppRequest,
    db: Session = Depends(get_db),
    current: dict = Depends(require_super_admin),
):
    """Register a new Flux app and create a single protocol-agnostic FDM deployment."""
    existing = (
        db.query(FluxAppRegistration)
        .filter(FluxAppRegistration.app_name == request.app_name)
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"App '{request.app_name}' is already registered",
        )

    app = FluxAppRegistration(
        app_name=request.app_name,
        protocol_ports=request.protocol_ports,
        is_active=True,
        registered_by=current["id"],
    )
    db.add(app)
    db.flush()

    from app.models.registered_tld import RegisteredTld

    tld = (
        db.query(RegisteredTld)
        .filter(
            RegisteredTld.purpose == "fdm",
            RegisteredTld.is_active == True,
        )
        .first()
    )
    base_domain = tld.domain if tld else settings.CLOUDFLARE_DOMAIN

    deployment = FdmDeployment(
        flux_app_name=request.app_name,
        region="XX",
        base_domain=base_domain,
        domain_pool_size=5,
        is_active=True,
        last_sync_status="never",
    )
    db.add(deployment)

    db.commit()
    db.refresh(app)

    logger.info(f"Super admin registered Flux app: {request.app_name}")

    return {
        "id": app.id,
        "app_name": app.app_name,
        "message": "App registered. Run sync to discover instances and detect regions.",
    }


@router.get("/apps/{app_id}")
async def get_app(
    app_id: int,
    db: Session = Depends(get_db),
    current: dict = Depends(require_super_admin),
):
    """Get details for a single registered Flux app."""
    app = db.query(FluxAppRegistration).filter(FluxAppRegistration.id == app_id).first()
    if not app:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="App not found"
        )

    regions, healthy_active, serving = _compute_app_health(db, app)

    return AppRegistrationResponse(
        id=app.id,
        app_name=app.app_name,
        protocol_ports=app.protocol_ports or {},
        is_active=app.is_active,
        registered_by=app.registered_by,
        last_discovery_at=app.last_discovery_at,
        last_discovery_ips=app.last_discovery_ips,
        created_at=app.created_at,
        updated_at=app.updated_at,
        regions=regions,
        healthy_instances=healthy_active,
        serving=serving,
    )


@router.put("/apps/{app_id}")
async def update_app(
    app_id: int,
    request: UpdateAppRequest,
    db: Session = Depends(get_db),
    current: dict = Depends(require_super_admin),
):
    """Update a Flux app registration (ports, active status)."""
    app = db.query(FluxAppRegistration).filter(FluxAppRegistration.id == app_id).first()
    if not app:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="App not found"
        )

    if request.protocol_ports is not None:
        app.protocol_ports = request.protocol_ports

    if request.is_active is not None:
        app.is_active = request.is_active
        db.query(FdmDeployment).filter(
            FdmDeployment.flux_app_name == app.app_name
        ).update({"is_active": request.is_active})

        # Goal-3 completeness (review I-1): toggling an app OFF must also
        # deactivate its ProtocolInstance rows so they leave the connection-string
        # JOIN -- mirrors delete_app:1447. (Toggle-ON re-creates PI via the
        # reconcile sync's _ensure_pi_for_fdm_domains phase, so no explicit
        # reactivate here.)
        if request.is_active is False:
            from app.models.ip_management import ProtocolInstance

            db.query(ProtocolInstance).filter(
                ProtocolInstance.flux_app_name == app.app_name
            ).update({"is_active": False}, synchronize_session=False)

        db.commit()
        # Operator-driven: reconcile THIS app now (no 30-min grace). Reactivation
        # also resets consecutive_failures inside reconcile_app so a former phantom
        # does not immediately re-deactivate.
        from app.tasks.fdm_tasks import reconcile_app as reconcile_app_task

        reconcile_app_task.delay(app.app_name)
        return {"message": f"App '{app.app_name}' updated; reconcile enqueued"}

    db.commit()
    return {"message": f"App '{app.app_name}' updated"}


@router.delete("/apps/{app_id}")
async def delete_app(
    app_id: int,
    db: Session = Depends(get_db),
    current: dict = Depends(require_super_admin),
):
    """Delete a Flux app registration with cascade cleanup (DNS-aware)."""
    app = db.query(FluxAppRegistration).filter(FluxAppRegistration.id == app_id).first()
    if not app:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="App not found"
        )

    from app.models.ip_management import ProtocolInstance
    from app.services.fdm import FdmSyncService

    deployments = (
        db.query(FdmDeployment)
        .filter(FdmDeployment.flux_app_name == app.app_name)
        .all()
    )
    deployment_ids = [d.id for d in deployments]

    if deployment_ids:
        # Clean DNS A-records BEFORE deleting rows (mirrors delete_tld at :1691).
        # Best-effort: a failed provider call must not block DB cleanup.
        domains = (
            db.query(FdmDomain)
            .filter(FdmDomain.deployment_id.in_(deployment_ids))
            .all()
        )
        sync = FdmSyncService(db)
        for domain in domains:
            try:
                await sync._delete_dns_record_for_domain(domain)
            except Exception as e:
                logger.warning(
                    f"delete_app DNS cleanup failed for {domain.domain_name}: {e}"
                )
        fdm_domain_query = db.query(FdmDomain).filter(
            FdmDomain.deployment_id.in_(deployment_ids)
        )
        fdm_domain_query.delete(synchronize_session=False)
        fdm_deployment_query = db.query(FdmDeployment).filter(
            FdmDeployment.id.in_(deployment_ids)
        )
        fdm_deployment_query.delete(synchronize_session=False)

    # Deactivate app-scoped ProtocolInstances so they leave the connection-string JOIN.
    db.query(ProtocolInstance).filter(
        ProtocolInstance.flux_app_name == app.app_name
    ).update({"is_active": False}, synchronize_session=False)

    db.delete(app)
    db.commit()

    return {
        "message": f"App '{app.app_name}' and {len(deployment_ids)} deployments deleted "
        f"({len(domains) if deployment_ids else 0} DNS records cleaned)"
    }


@router.post("/apps/{app_id}/sync")
async def sync_app(
    app_id: int,
    db: Session = Depends(get_db),
    current: dict = Depends(require_super_admin),
):
    """Trigger manual FDM sync for a registered app's deployments."""
    app = db.query(FluxAppRegistration).filter(FluxAppRegistration.id == app_id).first()
    if not app:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="App not found"
        )

    deployments = (
        db.query(FdmDeployment)
        .filter(
            FdmDeployment.flux_app_name == app.app_name,
            FdmDeployment.is_active == True,
        )
        .all()
    )

    if not deployments:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active deployments found for this app",
        )

    from app.tasks.fdm_tasks import sync_deployment

    results = []
    for deployment in deployments:
        task = sync_deployment.delay(deployment.id)
        results.append({"deployment_id": deployment.id, "task_id": task.id})

    app.last_discovery_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()

    return {
        "message": f"Sync triggered for {len(results)} deployments",
        "tasks": results,
    }


# ============================================================================
# PLATFORM SETTINGS
# ============================================================================


@router.get("/tlds/analytics", response_model=TldAnalyticsSnapshot)
async def get_tld_analytics(
    db: Session = Depends(get_db),
    current: dict = Depends(require_super_admin),
):
    """Live TLD usage snapshot. active_user_count per TLD is the SAME value
    the load-balancer uses (drift-proof). See spec §9."""
    from app.services.tlds.selection import TldSelectionService

    svc = TldSelectionService(db)
    snapshot = TldAnalyticsSnapshot()
    for purpose in PURPOSES:
        counts = svc.active_user_counts(purpose)
        tlds = (
            db.query(RegisteredTld)
            .filter(
                RegisteredTld.purpose == purpose, RegisteredTld.deleted_at.is_(None)
            )
            .order_by(RegisteredTld.is_active.desc(), RegisteredTld.id)
            .all()
        )
        # fdm-only DNS health (spec §4.3); {} for other purposes -> dns_health None
        dns_health = (
            svc.fdm_dns_health([t.id for t in tlds]) if purpose == "fdm" else {}
        )
        getattr(snapshot, purpose).extend(
            TldAnalyticsTld(
                tld_id=t.id,
                domain=t.domain,
                dns_provider=t.dns_provider,
                is_active=t.is_active,
                active_user_count=counts.get(t.id, 0),
                dns_health=TldDnsHealth(**dns_health[t.id])
                if t.id in dns_health
                else None,
            )
            for t in tlds
        )
    return snapshot


@router.get("/tlds/analytics/series", response_model=TldAnalyticsSeries)
async def get_tld_analytics_series(
    purpose: str = Query(..., pattern=r"^(fdm|subscription|dashboard|admin_panel)$"),
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    current: dict = Depends(require_super_admin),
):
    """Per-purpose daily time-series (chart-ready) from TldUsageDaily.
    Migration cliffs show for free: a deactivation is a same-day cliff
    (TLD-A -> 0, TLD-B -> +N). See spec §9."""
    cutoff = date.today() - timedelta(days=days)
    rows = (
        db.query(TldUsageDaily)
        .filter(TldUsageDaily.purpose == purpose, TldUsageDaily.snapshot_date >= cutoff)
        .order_by(TldUsageDaily.snapshot_date, TldUsageDaily.tld_id)
        .all()
    )
    by_date: dict[str, dict[str, int]] = {}
    domains: list[str] = []
    seen: set[str] = set()
    for r in rows:
        by_date.setdefault(r.snapshot_date.isoformat(), {})[
            r.domain_snapshot
        ] = r.active_user_count
        if r.domain_snapshot not in seen:
            seen.add(r.domain_snapshot)
            domains.append(r.domain_snapshot)
    return TldAnalyticsSeries(
        purpose=purpose,
        days=days,
        domains=domains,
        series=[
            TldAnalyticsSeriesDay(date=d, values=v) for d, v in sorted(by_date.items())
        ],
    )


@router.get("/tlds/assignments", response_model=TldAssignmentsResponse)
async def get_tld_assignments(
    db: Session = Depends(get_db),
    current: dict = Depends(require_super_admin),
):
    """Per-admin TLD assignment state for the /super/domains matrix.

    Admins with no AdminTldState row report nulls (they ride the LB default).
    See spec §5.4 / §10."""
    admins = (
        db.query(Admin).filter(Admin.status == "active").order_by(Admin.username).all()
    )
    states = db.query(AdminTldState).all()
    by_admin: dict[int, dict[str, AdminTldState]] = {}
    for s in states:
        by_admin.setdefault(s.admin_id, {})[s.purpose] = s

    out: list[TldAdminAssignment] = []
    for adm in admins:
        smap = by_admin.get(adm.id, {})
        cells: dict[str, TldAssignmentCell] = {}
        for purpose in PURPOSES:
            st = smap.get(purpose)
            cells[purpose] = TldAssignmentCell(
                effective_tld_id=st.effective_tld_id if st else None,
                pinned_tld_id=st.pinned_tld_id if st else None,
                source=st.source if st else None,
            )
        out.append(
            TldAdminAssignment(
                admin_id=adm.id, username=adm.username, assignments=cells
            )
        )
    return TldAssignmentsResponse(assignments=out)


@router.get("/settings/tlds", response_model=TldListResponse)
async def list_tlds(
    db: Session = Depends(get_db),
    current: dict = Depends(require_super_admin),
):
    all_tlds = (
        db.query(RegisteredTld)
        .order_by(RegisteredTld.purpose, RegisteredTld.is_active.desc())
        .all()
    )
    result = TldListResponse()
    for tld in all_tlds:
        tld_resp = TldResponse.model_validate(tld)
        if tld.purpose == "fdm":
            result.fdm.append(tld_resp)
        elif tld.purpose == "subscription":
            result.subscription.append(tld_resp)
        elif tld.purpose == "dashboard":
            result.dashboard.append(tld_resp)
        elif tld.purpose == "admin_panel":
            result.admin_panel.append(tld_resp)
    return result


@router.post("/settings/tlds", response_model=TldResponse)
async def create_tld(
    request: TldCreateRequest,
    db: Session = Depends(get_db),
    current: dict = Depends(require_super_admin),
):
    existing = (
        db.query(RegisteredTld)
        .filter(
            RegisteredTld.domain == request.domain,
            RegisteredTld.purpose == request.purpose,
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"TLD {request.domain} already registered for {request.purpose}",
        )

    if request.dns_provider == "arvancloud" and request.purpose == "fdm":
        # FDM: zone_id auto-set to domain (FDM creates subdomains under the base TLD)
        request.zone_id = request.zone_id or request.domain

    if request.dns_provider == "arvancloud" and not request.zone_id:
        raise HTTPException(
            status_code=422,
            detail="Zone domain is required for ArvanCloud (e.g., operator4.example.invalid)",
        )

    try:
        client = create_dns_client(
            provider=request.dns_provider,
            domain=request.domain,
            zone_id=request.zone_id,
        )
        async with client:
            if request.dns_provider == "cloudflare":
                await client.list_dns_records(per_page=1)
            else:
                # ArvanCloud: validate API key by listing account domains, not domain DNS records
                # (the domain may not be registered in ArvanCloud CDN yet)
                import aiohttp

                from app.core.database import SessionLocal
                from app.models.platform_settings import PlatformSetting

                db = SessionLocal()
                row = (
                    db.query(PlatformSetting)
                    .filter(PlatformSetting.key == "arvan_api_key")
                    .first()
                )
                api_key = row.value if row else ""
                db.close()
                async with aiohttp.ClientSession(
                    headers={"Authorization": f"ApiKey {api_key}"}
                ) as session:
                    async with session.get(
                        "https://napi.arvancloud.ir/cdn/4.0/domains",
                        params={"per_page": 1},
                    ) as resp:
                        if resp.status == 401:
                            raise ValueError("ArvanCloud API key is invalid")
                        if resp.status >= 500:
                            raise ValueError(f"ArvanCloud API returned {resp.status}")
    except Exception as e:
        raise HTTPException(
            status_code=422, detail=f"DNS provider validation failed: {str(e)}"
        )

    server_ip = None
    if request.purpose in ("subscription", "dashboard", "admin_panel"):
        server_ip = _detect_server_ip()

    tld = RegisteredTld(
        domain=request.domain,
        dns_provider=request.dns_provider,
        zone_id=request.zone_id,
        purpose=request.purpose,
        server_ip=server_ip,
        is_active=False,
    )
    db.add(tld)
    db.commit()
    db.refresh(tld)

    logger.info(
        f"Super admin {current['id']} registered TLD: {tld.domain} ({tld.purpose}, {tld.dns_provider})"
    )
    return TldResponse.model_validate(tld)


@router.delete("/settings/tlds/{tld_id}")
async def delete_tld(
    tld_id: int,
    db: Session = Depends(get_db),
    current: dict = Depends(require_super_admin),
):
    """Soft-delete a TLD. If active: last-active guard (>=2 for purpose) +
    migrate affected admins off (pins CLEARED — spec D8 delete path) + remove
    DNS, then set is_active=False and deleted_at. Never hard-deletes (assign_via_lb
    / resolve_effective already exclude deleted_at IS NOT NULL)."""
    from app.services.tlds.selection import NoActiveTld, TldSelectionService

    tld = db.query(RegisteredTld).filter(RegisteredTld.id == tld_id).first()
    if not tld:
        raise HTTPException(status_code=404, detail="TLD not found")
    if tld.deleted_at is not None:
        raise HTTPException(status_code=400, detail="TLD is already deleted")

    migrated: list = []
    cleared: list = []
    if tld.is_active:
        if _count_active_tlds(db, tld.purpose) <= 1:
            raise HTTPException(
                status_code=409,
                detail=f"Cannot delete the only active TLD for {tld.purpose}. "
                f"Activate another first.",
            )
        try:
            migrated, cleared = TldSelectionService(db).migrate_off(
                tld.id, clear_pinned=True
            )
        except NoActiveTld:
            db.rollback()
            raise HTTPException(
                status_code=409, detail="No other active TLD to migrate to"
            )
        tld.is_active = False

    # Remove the TLD's DNS A-record (best-effort via create_dns_client).
    try:
        client = create_dns_client(
            provider=tld.dns_provider,
            domain=tld.domain,
            zone_id=tld.zone_id,
        )
        async with client:
            record = await client.find_a_record_by_name(tld.domain)
            if record:
                await client.delete_dns_record(record["id"])
    except Exception as e:
        logger.warning(f"Failed to remove DNS for {tld.domain} on delete: {e}")

    # fdm-specific: remove this TLD's per-deployment subdomain DNS records + rows.
    # (Generic path above only removed the root A-record.) Delete is terminal (D8)
    # so rows go too -- unlike deactivate, which orphans them for re-activation.
    if tld.purpose == "fdm":
        from app.models.fdm import FdmDomain
        from app.services.fdm.fdm_sync_service import FdmSyncService

        sync = FdmSyncService(db)
        tld_domains = db.query(FdmDomain).filter(FdmDomain.tld_id == tld.id).all()
        for domain in tld_domains:
            try:
                await sync._delete_dns_record_for_domain(
                    domain
                )  # per-TLD-aware (4b.1.3)
            except Exception as e:
                logger.warning(
                    f"Failed to delete subdomain DNS for {domain.domain_name}: {e}"
                )
            db.delete(domain)

    # Remove the dynamic Traefik router (HTTP purposes). fail-open no-op
    # otherwise.
    from app.services.tlds.proxy_routes import deregister_route

    deregister_route(tld.domain)

    tld.deleted_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()

    _notify_tld_migration(db, migrated, cleared, "deleted")

    logger.info(
        f"Super admin {current['id']} soft-deleted TLD: {tld.domain} ({tld.purpose}) "
        f"- migrated {len(migrated)}, cleared {len(cleared)} pin(s)"
    )
    return {
        "success": True,
        "message": f"TLD {tld.domain} deleted",
        "migrated": migrated,
        "cleared_pins": cleared,
    }


@router.post("/settings/tlds/{tld_id}/activate", response_model=TldActivateResponse)
async def activate_tld(
    tld_id: int,
    db: Session = Depends(get_db),
    current: dict = Depends(require_super_admin),
):
    tld = db.query(RegisteredTld).filter(RegisteredTld.id == tld_id).first()
    if not tld:
        raise HTTPException(status_code=404, detail="TLD not found")

    if tld.is_active:
        raise HTTPException(
            status_code=400,
            detail=f"TLD {tld.domain} is already active for {tld.purpose}",
        )

    old_tld = (
        db.query(RegisteredTld)
        .filter(
            RegisteredTld.purpose == tld.purpose,
            RegisteredTld.is_active == True,
            RegisteredTld.id != tld.id,
        )
        .first()
    )
    old_domain = old_tld.domain if old_tld else None

    if tld.purpose == "fdm":
        details = await _activate_fdm_tld(db, tld, old_tld)
    elif tld.purpose == "subscription":
        details = await _activate_subscription_tld(db, tld, old_tld)
    elif tld.purpose == "dashboard":
        details = await _activate_dashboard_tld(db, tld, old_tld)
    elif tld.purpose == "admin_panel":
        details = await _activate_admin_panel_tld(db, tld, old_tld)
    else:
        raise HTTPException(status_code=400, detail=f"Unknown purpose: {tld.purpose}")

    logger.info(
        f"Super admin {current['id']} activated TLD: {tld.domain} ({tld.purpose}, {tld.dns_provider}) "
        f"- replaced {old_domain}"
    )

    return TldActivateResponse(
        success=True,
        message=f"TLD {tld.domain} activated for {tld.purpose}",
        purpose=tld.purpose,
        old_domain=old_domain,
        new_domain=tld.domain,
        details=details,
    )


@router.post("/settings/tlds/{tld_id}/deactivate", response_model=TldActivateResponse)
async def deactivate_tld(
    tld_id: int,
    db: Session = Depends(get_db),
    current: dict = Depends(require_super_admin),
):
    """Deactivate a TLD: last-active guard (>=2 active for the purpose), set
    inactive, then migrate affected admins off via TldSelectionService
    (pins PRESERVED — spec D8). Notifications are generalized in Phase 3."""
    from app.services.tlds.selection import NoActiveTld, TldSelectionService

    tld = db.query(RegisteredTld).filter(RegisteredTld.id == tld_id).first()
    if not tld:
        raise HTTPException(status_code=404, detail="TLD not found")
    if tld.deleted_at is not None:
        raise HTTPException(status_code=400, detail="TLD is already deleted")
    if not tld.is_active:
        raise HTTPException(status_code=400, detail=f"TLD {tld.domain} is not active")

    if _count_active_tlds(db, tld.purpose) <= 1:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot deactivate the only active TLD for {tld.purpose}. "
            f"Activate another first.",
        )

    tld.is_active = False
    try:
        affected, cleared = TldSelectionService(db).migrate_off(
            tld.id, clear_pinned=False
        )
    except NoActiveTld:
        db.rollback()
        raise HTTPException(status_code=409, detail="No other active TLD to migrate to")
    db.commit()

    # Tear down the dynamic Traefik router so a deactivated HTTP TLD stops
    # serving via the proxy (its DNS A-record is intentionally left for
    # re-activation; the router is re-created on activate). fail-open no-op for
    # fdm / when dynamic routing is disabled.
    from app.services.tlds.proxy_routes import deregister_route

    deregister_route(tld.domain)

    _notify_tld_migration(db, affected, cleared, "deactivated")

    logger.info(
        f"Super admin {current['id']} deactivated TLD: {tld.domain} ({tld.purpose}) "
        f"- migrated {len(affected)} admin(s)"
    )
    return TldActivateResponse(
        success=True,
        message=f"TLD {tld.domain} deactivated; {len(affected)} admin(s) migrated",
        purpose=tld.purpose,
        old_domain=tld.domain,
        new_domain=affected[0][3] if affected else tld.domain,
        details={"migrated": affected, "cleared_pins": cleared},
    )


@router.post("/settings/tlds/pin")
async def set_tld_pin(
    request: TldPinRequest,
    db: Session = Depends(get_db),
    current: dict = Depends(require_super_admin),
):
    """Pin an admin to a TLD for a purpose (tld_id set; effective becomes the
    pin) or clear the pin (tld_id=None; revert to least-active-user-count LB).
    Used by the Phase 2 pin dropdown; full per-admin UI lands in Phase 5."""
    from app.models.admin_tld_state import AdminTldState
    from app.services.tlds.selection import NoActiveTld, TldSelectionService

    svc = TldSelectionService(db)

    # Capture the OLD effective BEFORE the change (None if no state row yet).
    prior = (
        db.query(AdminTldState)
        .filter(
            AdminTldState.admin_id == request.admin_id,
            AdminTldState.purpose == request.purpose,
        )
        .first()
    )
    old_eff_id = prior.effective_tld_id if prior else None
    old_tld = db.get(RegisteredTld, old_eff_id) if old_eff_id else None
    old_domain = old_tld.domain if old_tld else None

    try:
        if request.tld_id is None:
            new_state = svc.clear_pin(request.admin_id, request.purpose)
        else:
            new_state = svc.set_pin(request.admin_id, request.purpose, request.tld_id)
        db.commit()
    except ValueError as e:
        # Invalid/inactive/unhealthy target TLD (set_pin guards). Surface a clean
        # 422 instead of an opaque 500, and leave the session usable.
        db.rollback()
        raise HTTPException(status_code=422, detail=str(e))
    except NoActiveTld as e:
        # clear_pin re-LBs and finds no active TLD for the purpose.
        db.rollback()
        raise HTTPException(status_code=409, detail=str(e))

    new_eff_id = new_state.effective_tld_id if new_state else None
    new_tld = db.get(RegisteredTld, new_eff_id) if new_eff_id else None
    new_domain = new_tld.domain if new_tld else None

    logger.info(
        f"Super admin {current['id']} set TLD pin: admin={request.admin_id} "
        f"purpose={request.purpose} tld_id={request.tld_id}"
    )

    _notify_tld_pin_change(
        db, request.admin_id, request.purpose, old_domain, new_domain
    )

    return {
        "success": True,
        "admin_id": request.admin_id,
        "purpose": request.purpose,
        "pinned_tld_id": request.tld_id,
    }


@router.get("/settings", response_model=PlatformSettingsResponse)
async def get_platform_settings(
    db: Session = Depends(get_db),
    current: dict = Depends(require_super_admin),
):
    """
    Get platform-wide settings.

    Returns key-value configuration: price per GB, price per region monthly,
    minimum topup tomans, and toman to USD exchange rate.
    """
    rows = db.query(PlatformSetting).all()
    settings_map = {row.key: row.value for row in rows}

    cf_token = settings_map.get(
        "cloudflare_api_token", settings.CLOUDFLARE_API_TOKEN or ""
    )
    arvan_key = settings_map.get("arvan_api_key", settings.ARVAN_API_KEY or "")

    return PlatformSettingsResponse(
        price_per_gb=settings_map.get("price_per_gb", "0"),
        price_per_region_monthly=settings_map.get("price_per_region_monthly", "0"),
        min_topup_tomans=settings_map.get("min_topup_tomans", "0"),
        toman_to_usd_rate=settings_map.get("toman_to_usd_rate", "0"),
        toman_per_usd_rate=settings_map.get("toman_per_usd_rate", "60000"),
        crypto_topup_address=settings_map.get("crypto_topup_address", ""),
        crypto_topup_network=settings_map.get("crypto_topup_network", ""),
        crypto_topup_memo=settings_map.get("crypto_topup_memo", ""),
        min_topup_usd=settings_map.get("min_topup_usd", "10"),
        cloudflare_domain=settings_map.get(
            "cloudflare_domain", settings.CLOUDFLARE_DOMAIN
        ),
        cloudflare_zone_id=settings_map.get(
            "cloudflare_zone_id", settings.CLOUDFLARE_ZONE_ID or ""
        ),
        cloudflare_api_token=cf_token,
        arvan_api_key=arvan_key,
    )


@router.put("/settings", response_model=PlatformSettingsResponse)
async def update_platform_settings(
    request: UpdateSettingsRequest,
    db: Session = Depends(get_db),
    current: dict = Depends(require_super_admin),
):
    """
    Update platform-wide settings.

    Only updates fields that are explicitly provided (not None).
    Creates the setting row if it does not exist.
    """
    update_data = request.model_dump(exclude_unset=True)

    for key, value in update_data.items():
        if value is None:
            continue

        setting = db.query(PlatformSetting).filter(PlatformSetting.key == key).first()
        if setting:
            setting.value = value
        else:
            setting = PlatformSetting(key=key, value=value)
            db.add(setting)

    db.commit()

    logger.info(
        f"Super admin {current['id']} updated platform settings: {list(update_data.keys())}"
    )

    # Return updated settings
    return await get_platform_settings(db=db, current=current)


@router.post("/settings/migrate-tld", response_model=MigrateTldResponse)
async def migrate_tld(
    request: MigrateTldRequest,
    db: Session = Depends(get_db),
    current: dict = Depends(require_super_admin),
):
    """
    DEPRECATED: Use POST /settings/tlds/{id}/activate instead.

    Migrate the platform to a new TLD.

    Cascade operation:
    1. Read current domain from DNS config
    2. Delete all Cloudflare DNS records for the OLD domain/zone
    3. Save new domain + zone_id to platform_settings
    4. Update all FdmDeployment.base_domain rows
    5. Regenerate all FdmDomain.domain_name values (replace TLD suffix)
    6. Clear dns_record_id on all domains
    7. Trigger full FDM sync
    """
    if not request.confirm:
        raise HTTPException(
            status_code=400,
            detail=(
                "Set confirm=true to proceed. This is a destructive, "
                "superseded operation -- prefer POST /settings/tlds/{id}/activate."
            ),
        )

    import asyncio

    from app.services.dns_config import get_dns_config
    from app.services.fdm.cloudflare_client import CloudflareDnsClient
    from app.services.fdm.fdm_sync_service import FdmSyncService

    # 1. Read current DNS config
    current_config = get_dns_config(
        db,
        fallback_domain=settings.CLOUDFLARE_DOMAIN,
        fallback_zone_id=settings.CLOUDFLARE_ZONE_ID,
        fallback_api_token=settings.CLOUDFLARE_API_TOKEN,
    )
    if not current_config:
        raise HTTPException(
            status_code=500,
            detail="Current DNS configuration is incomplete. Cannot migrate.",
        )

    old_domain = current_config.domain

    if old_domain == request.new_domain:
        raise HTTPException(
            status_code=400,
            detail=f"New domain is the same as current domain: {old_domain}",
        )

    # 2. Delete all Cloudflare DNS records for OLD zone
    dns_records_deleted = 0
    dns_delete_errors = 0

    all_domains = db.query(FdmDomain).filter(FdmDomain.dns_record_id.isnot(None)).all()

    if all_domains:
        try:
            async with CloudflareDnsClient(
                api_token=current_config.api_token,
                zone_id=current_config.zone_id,
                domain=old_domain,
            ) as cf_client:
                for domain in all_domains:
                    try:
                        await cf_client.delete_dns_record(domain.dns_record_id)
                        dns_records_deleted += 1
                    except Exception as e:
                        logger.warning(
                            f"Failed to delete DNS record {domain.dns_record_id}: {e}"
                        )
                        dns_delete_errors += 1
        except Exception as e:
            logger.error(f"Failed to connect to Cloudflare for cleanup: {e}")
            dns_delete_errors = len(all_domains)

    # 3. Save new domain + zone_id to platform_settings
    for key, value in [
        ("cloudflare_domain", request.new_domain),
        ("cloudflare_zone_id", request.new_zone_id),
    ]:
        setting = db.query(PlatformSetting).filter(PlatformSetting.key == key).first()
        if setting:
            setting.value = value
        else:
            db.add(PlatformSetting(key=key, value=value))
    db.flush()

    # 4. Update all FdmDeployment.base_domain rows
    deployments = db.query(FdmDeployment).all()
    for deployment in deployments:
        deployment.base_domain = request.new_domain
    db.flush()
    deployments_updated = len(deployments)

    # 5. Regenerate all FdmDomain.domain_name values (replace TLD suffix only)
    all_domain_records = db.query(FdmDomain).all()
    domains_renamed = 0
    for domain_record in all_domain_records:
        old_name = domain_record.domain_name
        if old_name.endswith(f".{old_domain}"):
            subdomain = old_name[: -(len(old_domain) + 1)]
            domain_record.domain_name = f"{subdomain}.{request.new_domain}"
            domains_renamed += 1
        domain_record.dns_record_id = None  # 6. Clear old Cloudflare record IDs
        domain_record.health_status = "unknown"
    db.commit()

    # 7. Trigger full FDM sync
    sync_triggered = False
    try:
        sync_service = FdmSyncService(db)
        asyncio.create_task(sync_service.sync_all_deployments())
        sync_triggered = True
    except Exception as e:
        logger.error(f"Failed to trigger FDM sync: {e}")

    logger.info(
        f"Super admin {current['id']} migrated TLD: {old_domain} -> {request.new_domain} "
        f"({deployments_updated} deployments, {domains_renamed} domains, "
        f"{dns_records_deleted} DNS records deleted)"
    )

    return MigrateTldResponse(
        success=True,
        message=f"TLD migrated from {old_domain} to {request.new_domain}. FDM sync {'triggered' if sync_triggered else 'FAILED - trigger manually'}.",
        old_domain=old_domain,
        new_domain=request.new_domain,
        deployments_updated=deployments_updated,
        domains_renamed=domains_renamed,
        dns_records_deleted=dns_records_deleted,
        dns_delete_errors=dns_delete_errors,
        sync_triggered=sync_triggered,
    )
