"""
Admin API Endpoints for FluxVPN Reseller Platform

Administrative interface for managing end users, wallet, wire orders,
connection strings, region assignments, and per-admin analytics.

All endpoints require 'admin' role via require_admin dependency.
All queries enforce data isolation by filtering on admin_id from JWT.
"""

import logging
import re
import secrets
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from app.core.auth.password import hash_password
from app.core.auth.role_dependencies import RoleChecker, require_admin
from app.core.constants import (
    MACRO_REGIONS,
    country_flag,
    get_country_name,
    get_macro_region_name,
)
from app.core.database import get_db
from app.models.admin_packages import AdminPackage
from app.models.admin_users import AdminUser
from app.models.fdm import FdmDeployment
from app.models.platform_settings import PlatformSetting
from app.models.traffic_logs import TrafficLog
from app.models.user_adjustments import UserAdjustment
from app.models.user_regions import UserRegion
from app.schemas.admin_api import (
    AdminAnalytics,
    ConnectionStringsResponse,
    CountryInfo,
    CreateUserRequest,
    MacroRegionInfo,
    PanelUrlResponse,
    PaymentConfigResponse,
    ProtocolBreakdownEntry,
    RegionInfo,
    TopUserTraffic,
    TransactionListResponse,
    TransactionResponse,
    UpdateUserRequest,
    UserCreateResponse,
    UserDetailResponse,
    UserListResponse,
    UserResponse,
    WalletResponse,
    WireOrderRequest,
    WireOrderResponse,
)
from app.schemas.user_adjustments import (
    RenewUserRequest,
    ResetTrafficRequest,
    SetTelegramRequest,
    SetUsernameRequest,
    SetUserRegionsRequest,
)
from app.services.billing.wallet_service import WalletService
from app.services.billing.wire_order_service import WireOrderService
from app.services.credentials.connection_string_service import ConnectionStringService
from app.services.credentials.reseller_credential_service import CredentialService
from app.services.credentials.username_generator import (
    generate_unique_username,
    username_taken,
)
from app.services.regions import availability
from app.services.subscriptions.adjustment_service import AdjustmentService
from app.services.url_resolver import (
    get_dashboard_base_url,
    get_subscription_base_url,
    resolve_admin_panel_url,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["Admin API"])

# Bytes to GB conversion factor
BYTES_PER_GB = 1024**3


# ============================================================================
# HELPERS
# ============================================================================


def _verify_user_ownership(user: AdminUser, admin_id: int) -> None:
    """Verify that the user belongs to the requesting admin. Raises 404 if not."""
    if user.admin_id != admin_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )


def _build_user_response(user: AdminUser, db: Session) -> UserResponse:
    """Build a UserResponse from an AdminUser."""
    from app.core.config import settings

    traffic_gb = (
        float(user.traffic_used_bytes or 0) / BYTES_PER_GB
        if user.traffic_used_bytes
        else 0.0
    )
    traffic_limit_gb = (
        float(user.traffic_limit_bytes) / BYTES_PER_GB
        if user.traffic_limit_bytes
        else None
    )

    macro_region = user.region.macro_region if user.region else None

    subscription_url = None
    if user.subscription_token:
        subscription_url = f"{get_subscription_base_url(db, user.admin_id)}/api/v1/user/sub/{user.subscription_token}"

    return UserResponse(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        remark=user.remark,
        status=user.status,
        traffic_used_gb=round(traffic_gb, 4),
        traffic_limit_gb=round(traffic_limit_gb, 4) if traffic_limit_gb else None,
        macro_region=macro_region,
        subscription_url=subscription_url,
        expires_at=user.expires_at,
        created_at=user.created_at,
    )


def _build_user_detail_response(user: AdminUser, db: Session) -> UserDetailResponse:
    """Build UserDetailResponse with macro region info."""
    traffic_gb = (
        float(user.traffic_used_bytes or 0) / BYTES_PER_GB
        if user.traffic_used_bytes
        else 0.0
    )
    traffic_limit_gb = (
        float(user.traffic_limit_bytes) / BYTES_PER_GB
        if user.traffic_limit_bytes
        else None
    )

    macro_region_info = None
    if user.region:
        macro_region_info = RegionInfo(
            macro_region=user.region.macro_region,
            assigned_at=user.region.activated_at,
        )

    from app.core.config import settings

    subscription_url = None
    if user.subscription_token:
        subscription_url = f"{get_subscription_base_url(db, user.admin_id)}/api/v1/user/sub/{user.subscription_token}"

    adjustments = (
        db.query(UserAdjustment)
        .filter(UserAdjustment.user_id == user.id)
        .order_by(UserAdjustment.created_at.desc())
        .limit(50)
        .all()
    )

    return UserDetailResponse(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        remark=user.remark,
        status=user.status,
        traffic_used_gb=round(traffic_gb, 4),
        traffic_limit_gb=round(traffic_limit_gb, 4) if traffic_limit_gb else None,
        macro_region=user.region.macro_region if user.region else None,
        macro_region_info=macro_region_info,
        subscription_url=subscription_url,
        expires_at=user.expires_at,
        created_at=user.created_at,
        macro_regions=[r.macro_region for r in user.regions],
        telegram_id=user.telegram_id,
        telegram_chat_id=user.telegram_chat_id,
        adjustments=[
            {
                "id": a.id,
                "action": a.action,
                "details": a.details,
                "reason": a.reason,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in adjustments
        ],
    )


# ============================================================================
# DYNAMIC REGIONS
# ============================================================================


@router.get("/available-regions")
async def get_available_regions(
    db: Session = Depends(get_db),
    current: dict = Depends(RoleChecker(["admin", "super_admin"])),
):
    """
    Get available macro regions with healthy FDM deployments.

    Returns 4 macro regions with per-country breakdown.
    """
    from app.services.regions.availability import macro_region_availability

    result = []
    for entry in macro_region_availability(db):
        result.append(
            MacroRegionInfo(
                code=entry["code"],
                name=entry["name"],
                flag=entry["flag"],
                healthy_instances=entry["healthy_instances"],
                countries=[CountryInfo(**c) for c in entry["countries"]],
            )
        )
    return result


# ============================================================================
# END USER CRUD
# ============================================================================


@router.get("/users")
async def list_users(
    status_filter: str | None = Query(None, alias="status"),
    search: str | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current: dict = Depends(require_admin),
):
    """
    List end users belonging to this admin with pagination.

    Filter by status and search by username.
    """
    admin_id: int = current["id"]

    query = db.query(AdminUser).filter(AdminUser.admin_id == admin_id)

    if status_filter:
        query = query.filter(AdminUser.status == status_filter)
    if search:
        pattern = f"%{search}%"
        query = query.filter(AdminUser.username.ilike(pattern))

    total = query.count()

    users = (
        query.order_by(desc(AdminUser.created_at))
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    items = [_build_user_response(u, db) for u in users]

    return UserListResponse(items=items, total=total, page=page, per_page=per_page)


@router.post(
    "/users",
    status_code=status.HTTP_201_CREATED,
)
async def create_user(
    request: CreateUserRequest,
    db: Session = Depends(get_db),
    current: dict = Depends(RoleChecker(["admin", "super_admin"])),
):
    """
    Create an end user with auto-generated VPN credentials.

    Generates a random portal password (8 chars), VPN credentials for all
    protocols, and assigns a macro region.
    """
    admin_id: int = current["id"]

    # Resolve username: explicit override wins, else generate a non-leaking one.
    if request.username:
        username = request.username
        # Global, case-insensitive: usernames key VPN clients across resellers.
        if username_taken(db, username):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Username '{username}' already exists",
            )
    else:
        try:
            username = generate_unique_username(db, admin_id)
        except RuntimeError:
            logger.exception(
                "username generation exhausted for admin_id=%s",
                admin_id,
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Could not generate a unique username right now; please retry.",
            )

    # Generate random portal password
    portal_password = secrets.token_urlsafe(6)  # 8 chars base64url

    user = AdminUser(
        admin_id=admin_id,
        username=username,
        password_hash=hash_password(portal_password),
        display_name=request.display_name,
        remark=request.remark,
        status="active",
        traffic_limit_bytes=int(request.traffic_limit_gb * BYTES_PER_GB)
        if request.traffic_limit_gb
        else None,
        subscription_token=secrets.token_hex(16),
        expires_at=request.expires_at,
    )
    db.add(user)
    db.flush()  # Flush to get user.id for credential generation

    # Generate VPN credentials for all protocols
    cred_service = CredentialService(db)
    cred_service.generate_user_credentials(user)

    # Assign macro region
    if request.macro_region:
        macro_region = request.macro_region.lower()
        if macro_region not in MACRO_REGIONS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid macro region. Must be one of: {list(MACRO_REGIONS.keys())}",
            )
    else:
        # Auto-assign: pick the macro region with most healthy domains
        from app.models.fdm import FdmDomain

        country_counts = dict(
            db.query(
                func.upper(FdmDeployment.region).label("code"),
                func.count(FdmDomain.id).label("domain_count"),
            )
            .join(FdmDomain, FdmDomain.deployment_id == FdmDeployment.id)
            .filter(
                FdmDeployment.is_active == True,
                FdmDomain.health_status == "healthy",
                FdmDeployment.region != "XX",
            )
            .group_by(func.upper(FdmDeployment.region))
            .all()
        )

        macro_counts = {}
        for macro_code, info in MACRO_REGIONS.items():
            macro_counts[macro_code] = sum(
                country_counts.get(c, 0) for c in info["countries"]
            )
        macro_region = (
            max(macro_counts, key=lambda k: macro_counts[k]) if macro_counts else "eu"
        )

    if macro_region:
        user_region = UserRegion(
            user_id=user.id,
            macro_region=macro_region,
            is_primary=True,
        )
        db.add(user_region)

    db.commit()
    db.refresh(user)

    # Generate connection strings for the macro region
    connection_strings = {}
    if macro_region:
        conn_service = ConnectionStringService(db)
        connection_strings = conn_service.generate_connection_strings(
            user, macro_region
        )

    # Build portal URL
    portal_url = None
    if user.id:
        from app.core.config import settings

        portal_url = f"{get_dashboard_base_url(db, user.admin_id)}/user/login"

    logger.info(
        f"Admin {admin_id} created end user {user.username} (id={user.id}, macro_region={macro_region})"
    )

    # --- Push notification to admin ---
    try:
        from app.models.admins import Admin
        from app.services.notifications.send_alert import send_telegram_alert
        from app.services.notifications.templates import format_user_created

        admin = db.query(Admin).filter(Admin.id == admin_id).first()
        if admin and admin.telegram_id and str(admin.telegram_id).isdigit():
            chat_id = int(admin.telegram_id)

            region_name = (
                get_macro_region_name(macro_region) if macro_region else "Auto"
            )

            from app.core.config import settings as app_settings

            monitoring_url = (
                f"{get_dashboard_base_url(db, user.admin_id)}/user/{user.username}"
            )
            subscription_url = f"{get_subscription_base_url(db, user.admin_id)}/api/v1/user/sub/{user.subscription_token}"

            msg = format_user_created(
                username=user.username,
                password=portal_password,
                macro_region=macro_region or "N/A",
                region_name=region_name,
                traffic_limit_gb=request.traffic_limit_gb,
                connection_strings=connection_strings,
                monitoring_url=monitoring_url,
                subscription_url=subscription_url,
            )
            send_telegram_alert(chat_id, msg)
    except Exception as e:
        logger.warning(f"Failed to send user creation notification: {e}")

    response = _build_user_response(user, db)
    return UserCreateResponse(
        id=response.id,
        username=response.username,
        display_name=response.display_name,
        remark=response.remark,
        status=response.status,
        traffic_used_gb=response.traffic_used_gb,
        traffic_limit_gb=response.traffic_limit_gb,
        macro_region=response.macro_region,
        created_at=response.created_at,
        password=portal_password,
        connection_strings=connection_strings,
        portal_url=portal_url,
    )


@router.get("/users/{user_id}")
async def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    current: dict = Depends(require_admin),
):
    """
    Get detailed information for a specific end user.

    Includes traffic stats, region assignments, and credential status.
    Verifies user belongs to this admin.
    """
    admin_id: int = current["id"]

    user = db.query(AdminUser).filter(AdminUser.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    _verify_user_ownership(user, admin_id)

    return _build_user_detail_response(user, db)


@router.put("/users/{user_id}")
async def update_user(
    user_id: int,
    request: UpdateUserRequest,
    db: Session = Depends(get_db),
    current: dict = Depends(require_admin),
):
    """
    Update an end user's display name, remark, or reset password.

    Verifies user belongs to this admin.
    """
    admin_id: int = current["id"]

    user = db.query(AdminUser).filter(AdminUser.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    _verify_user_ownership(user, admin_id)

    updated_fields = []
    if request.display_name is not None:
        user.display_name = request.display_name
        updated_fields.append("display_name")
    if request.remark is not None:
        user.remark = request.remark
        updated_fields.append("remark")
    if request.new_password is not None:
        user.password_hash = hash_password(request.new_password)
        AdjustmentService(db).record_password_reset(user, admin_id)
        updated_fields.append("password")
    if request.traffic_limit_gb is not None:
        # Route through AdjustmentService so the change is audited (writes a
        # UserAdjustment row). Preserve the edit-form's existing semantics:
        # 0 / falsy => unlimited (None).
        gb = request.traffic_limit_gb if request.traffic_limit_gb else None
        AdjustmentService(db).set_traffic_limit(user, admin_id, gb, None)
        updated_fields.append("traffic_limit")
    if "expires_at" in request.model_fields_set:
        user.expires_at = request.expires_at
        updated_fields.append("expires_at")

    if not updated_fields:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update",
        )

    db.commit()
    db.refresh(user)

    logger.info(f"Admin {admin_id} updated user {user.username}: {updated_fields}")

    return _build_user_response(user, db)


@router.post("/users/{user_id}/renew")
async def renew_user(
    user_id: int,
    request: RenewUserRequest,
    db: Session = Depends(get_db),
    current: dict = Depends(require_admin),
):
    """Manual renewal / adjustment. Exactly one action field must be set. Audited."""
    admin_id: int = current["id"]
    user = db.query(AdminUser).filter(AdminUser.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    _verify_user_ownership(user, admin_id)

    provided = [
        f
        for f in ("extend_days", "topup_gb", "set_expiry", "reapply_package_id")
        if getattr(request, f) is not None
    ]
    if request.set_unlimited or request.set_traffic_limit_gb is not None:
        provided.append("set_traffic_limit")
    if len(provided) != 1:
        raise HTTPException(
            status_code=400, detail="Provide exactly one adjustment action"
        )

    svc = AdjustmentService(db)
    if request.extend_days is not None:
        svc.extend_days(user, admin_id, request.extend_days, request.reason)
    elif request.topup_gb is not None:
        svc.topup_gb(user, admin_id, request.topup_gb, request.reason)
    elif request.set_expiry is not None:
        svc.set_expiry(user, admin_id, request.set_expiry, request.reason)
    elif request.set_unlimited or request.set_traffic_limit_gb is not None:
        gb = None if request.set_unlimited else request.set_traffic_limit_gb
        if gb is not None and gb <= 0:
            raise HTTPException(
                status_code=400,
                detail="Traffic limit must be greater than 0 GB. "
                "Use the Unlimited option for no cap, or suspend the user to block access.",
            )
        svc.set_traffic_limit(user, admin_id, gb, request.reason)
    else:
        pkg = (
            db.query(AdminPackage)
            .filter(
                AdminPackage.id == request.reapply_package_id,
                AdminPackage.admin_id == admin_id,
            )
            .first()
        )
        if not pkg:
            raise HTTPException(status_code=404, detail="Package not found")
        svc.reapply_plan(user, admin_id, pkg, request.reason)

    db.commit()
    db.refresh(user)
    return _build_user_detail_response(user, db)


@router.put("/users/{user_id}/regions")
async def set_user_regions_endpoint(
    user_id: int,
    request: SetUserRegionsRequest,
    db: Session = Depends(get_db),
    current: dict = Depends(require_admin),
):
    """Replace a user's region set. Availability-validated + audited."""
    admin_id: int = current["id"]
    user = db.query(AdminUser).filter(AdminUser.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    _verify_user_ownership(user, admin_id)

    regions = list(dict.fromkeys(r.lower() for r in request.macro_regions))
    invalid = [r for r in regions if r not in MACRO_REGIONS]
    if invalid:
        raise HTTPException(status_code=400, detail=f"Invalid regions: {invalid}")

    healthy = availability.healthy_macro_codes(db)
    unavailable = [r for r in regions if r not in healthy]
    if unavailable:
        raise HTTPException(
            status_code=400, detail=f"Regions unavailable: {unavailable}"
        )

    AdjustmentService(db).edit_regions(user, admin_id, regions, request.reason)
    db.commit()
    db.refresh(user)
    return _build_user_detail_response(user, db)


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current: dict = Depends(require_admin),
):
    """
    Delete an end user and all their credentials and traffic logs.

    Verifies user belongs to this admin.
    """
    admin_id: int = current["id"]

    user = db.query(AdminUser).filter(AdminUser.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    _verify_user_ownership(user, admin_id)

    # Delete traffic logs first (no FK cascade)
    traffic_count = (
        db.query(TrafficLog)
        .filter(TrafficLog.user_id == user_id)
        .delete(synchronize_session=False)
    )

    # Decrement domain load before deletion
    css = ConnectionStringService(db)
    css.decrement_domain_on_user_change(user_id)

    # Delete VPN credentials via service
    cred_service = CredentialService(db)
    cred_service.delete_user_credentials(user_id)

    # Delete the user (cascade will handle regions)
    deleted_username = user.username
    db.delete(user)
    db.commit()
    logger.info(
        "USER_DELETE action=delete user_id=%s username=%s actor_admin_id=%s traffic_logs_purged=%s",
        user_id,
        deleted_username,
        admin_id,
        traffic_count,
    )

    return {"success": True, "message": f"User '{deleted_username}' deleted"}


@router.post("/users/{user_id}/toggle")
async def toggle_user_status(
    user_id: int,
    db: Session = Depends(get_db),
    current: dict = Depends(require_admin),
):
    """
    Toggle an end user between active and suspended.

    Verifies user belongs to this admin.
    """
    admin_id: int = current["id"]

    user = db.query(AdminUser).filter(AdminUser.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    _verify_user_ownership(user, admin_id)

    active_now = user.status == "active"
    # Decrement domain load when suspending
    if active_now:
        css = ConnectionStringService(db)
        css.decrement_domain_on_user_change(user.id)
    AdjustmentService(db).set_status(user, admin_id, active=not active_now)
    db.commit()
    db.refresh(user)
    return {"success": True, "message": f"User '{user.username}' is now {user.status}"}


@router.post("/users/{user_id}/regenerate-sub-token")
def regenerate_subscription_token(
    user_id: int,
    db: Session = Depends(get_db),
    current: dict = Depends(RoleChecker(["admin", "super_admin"])),
):
    """Regenerate subscription token for an end user (invalidates old link)."""
    user = (
        db.query(AdminUser)
        .filter(AdminUser.id == user_id, AdminUser.admin_id == current["id"])
        .first()
    )
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.subscription_token = secrets.token_hex(16)
    db.commit()
    db.refresh(user)

    return _build_user_detail_response(user, db)


@router.put("/users/{user_id}/username")
async def set_username_endpoint(
    user_id: int,
    request: SetUsernameRequest,
    db: Session = Depends(get_db),
    current: dict = Depends(require_admin),
):
    """Rename an end user + re-provision username-dependent credentials. Audited."""
    admin_id: int = current["id"]
    user = db.query(AdminUser).filter(AdminUser.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    _verify_user_ownership(user, admin_id)
    try:
        AdjustmentService(db).set_username(
            user, admin_id, request.new_username, request.reason
        )
    except ValueError as e:
        code = str(e)
        if code == "username_unchanged":
            # Idempotent no-op: renaming to the current name changes nothing.
            return _build_user_detail_response(user, db)
        if code == "username_taken":
            raise HTTPException(status_code=409, detail="Username already in use")
        raise HTTPException(status_code=400, detail=f"Invalid username ({code})")
    db.commit()
    db.refresh(user)
    return _build_user_detail_response(user, db)


@router.put("/users/{user_id}/telegram")
async def set_telegram_endpoint(
    user_id: int,
    request: SetTelegramRequest,
    db: Session = Depends(get_db),
    current: dict = Depends(require_admin),
):
    """Edit or detach an end user's Telegram id/chat_id. Audited."""
    admin_id: int = current["id"]
    user = db.query(AdminUser).filter(AdminUser.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    _verify_user_ownership(user, admin_id)
    try:
        AdjustmentService(db).set_telegram(
            user,
            admin_id,
            request.telegram_id,
            request.telegram_chat_id,
            request.reason,
        )
    except ValueError:
        raise HTTPException(
            status_code=409, detail="Telegram id already in use for this reseller"
        )
    db.commit()
    db.refresh(user)
    return _build_user_detail_response(user, db)


@router.post("/users/{user_id}/reset-traffic")
async def reset_traffic_endpoint(
    user_id: int,
    request: ResetTrafficRequest | None = None,
    db: Session = Depends(get_db),
    current: dict = Depends(require_admin),
):
    """Reset an end user's used traffic to 0. Audited. Body optional (reason)."""
    admin_id: int = current["id"]
    user = db.query(AdminUser).filter(AdminUser.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    _verify_user_ownership(user, admin_id)
    reason = request.reason if request else None
    AdjustmentService(db).reset_used_traffic(user, admin_id, reason)
    db.commit()
    db.refresh(user)
    return _build_user_detail_response(user, db)


# ============================================================================
# CONNECTION STRINGS
# ============================================================================


@router.get("/users/{user_id}/connections")
async def get_user_connections(
    user_id: int,
    db: Session = Depends(get_db),
    current: dict = Depends(require_admin),
):
    """
    Get all connection strings for a user across all assigned regions.

    Uses ConnectionStringService to generate protocol-specific connection URLs
    via FDM DNS domains. Verifies user belongs to this admin.
    """
    admin_id: int = current["id"]

    user = db.query(AdminUser).filter(AdminUser.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    _verify_user_ownership(user, admin_id)

    conn_service = ConnectionStringService(db)
    connections = conn_service.generate_all_region_connections(user)
    telegram_proxies = conn_service.generate_telegram_proxy_links(user)

    return ConnectionStringsResponse(
        connections=connections,
        telegram_proxies=telegram_proxies,
        last_refreshed_at=user.last_connection_refresh_at,
    )


@router.post("/users/{user_id}/refresh-connections")
async def refresh_user_connections(
    user_id: int,
    db: Session = Depends(get_db),
    current: dict = Depends(require_admin),
):
    """Refresh connection strings for a user. Rate-limited to once per 4 hours."""
    admin_id: int = current["id"]

    user = db.query(AdminUser).filter(AdminUser.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    _verify_user_ownership(user, admin_id)

    # Rate limit check
    if user.last_connection_refresh_at:
        elapsed = (
            datetime.now(timezone.utc).replace(tzinfo=None)
            - user.last_connection_refresh_at
        )
        if elapsed < timedelta(hours=4):
            retry_at = user.last_connection_refresh_at + timedelta(hours=4)
            raise HTTPException(
                status_code=429,
                detail=f"Refresh available at {retry_at.isoformat()}",
            )

    user.last_connection_refresh_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()

    conn_service = ConnectionStringService(db)
    connections = conn_service.generate_all_region_connections(user)
    telegram_proxies = conn_service.generate_telegram_proxy_links(user)

    return ConnectionStringsResponse(
        connections=connections,
        telegram_proxies=telegram_proxies,
        last_refreshed_at=user.last_connection_refresh_at,
    )


@router.post("/users/{user_id}/reset-password")
async def reset_user_password(
    user_id: int,
    db: Session = Depends(get_db),
    current: dict = Depends(require_admin),
):
    """Generate a new random password for the user and return it."""
    admin_id: int = current["id"]

    user = db.query(AdminUser).filter(AdminUser.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    _verify_user_ownership(user, admin_id)

    new_password = secrets.token_urlsafe(6)[:8]
    user.password_hash = hash_password(new_password)
    AdjustmentService(db).record_password_reset(user, admin_id)
    db.commit()

    return {"password": new_password}


@router.post("/users/{user_id}/send-connections")
async def send_connections_to_telegram(
    user_id: int,
    db: Session = Depends(get_db),
    current: dict = Depends(require_admin),
):
    """Generate new password and send full credentials to admin's Telegram."""
    admin_id: int = current["id"]

    user = db.query(AdminUser).filter(AdminUser.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    _verify_user_ownership(user, admin_id)

    from app.models.admins import Admin

    admin = db.query(Admin).filter(Admin.id == admin_id).first()
    if not admin or not admin.telegram_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No Telegram account linked to your admin profile",
        )

    # Generate new password
    new_password = secrets.token_urlsafe(6)[:8]
    user.password_hash = hash_password(new_password)
    db.commit()

    conn_service = ConnectionStringService(db)
    all_connections = conn_service.generate_all_region_connections(user)

    # Build message
    lines = [
        f"Username: {user.username}",
        f"Password: {new_password}",
    ]

    # Macro region header
    from app.models.user_regions import UserRegion

    user_region = db.query(UserRegion).filter(UserRegion.user_id == user.id).first()
    if user_region:
        region_info = MACRO_REGIONS.get(user_region.macro_region, {})
        lines.append(
            f"Region: {region_info.get('flag', '')} {region_info.get('name', user_region.macro_region)}"
        )

    traffic_gb = (
        (user.traffic_limit_bytes / BYTES_PER_GB) if user.traffic_limit_bytes else None
    )
    traffic = f"{traffic_gb:.1f} GB" if traffic_gb else "Unlimited"
    lines.append(f"Traffic: {traffic}")

    for country_code, protocols in all_connections.items():
        flag = country_flag(country_code)
        name = get_country_name(country_code)
        lines.append("")
        lines.append(f"{flag} {name}")
        for proto, pc in protocols.items():
            uri = (
                pc.get("primary", "")
                if isinstance(pc, dict)
                else getattr(pc, "primary", "")
            )
            if uri:
                lines.append(f"  {proto.upper()}: {uri}")

    lines.append("")
    from app.core.config import settings

    lines.append(
        f"Dashboard: {get_dashboard_base_url(db, user.admin_id)}/user/{user.username}"
    )

    # Add Telegram proxy links
    tg_links = conn_service.generate_telegram_proxy_links(user)
    if tg_links:
        lines.append("")
        lines.append("Telegram Proxy:")
        for country_code, link in tg_links.items():
            lines.append(link)

    from app.services.notifications.send_alert import send_telegram_alert

    tid = str(admin.telegram_id).strip()
    chat_id: int | str = int(tid) if tid.isdigit() else tid
    success = send_telegram_alert(chat_id, "\n".join(lines))

    if not success:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to send Telegram message",
        )

    return {"message": "Sent to Telegram", "new_password": new_password}


# ============================================================================
# WALLET & WIRE ORDERS
# ============================================================================


@router.get("/wallet")
async def get_wallet(
    db: Session = Depends(get_db),
    current: dict = Depends(RoleChecker(["admin", "super_admin"])),
):
    """
    Get wallet balance and recent 10 transactions for the authenticated admin.
    """
    admin_id: int = current["id"]

    wallet_service = WalletService(db)
    balance = float(wallet_service.get_balance(admin_id))

    # Recent 10 transactions
    txns_result = wallet_service.get_transactions(admin_id, page=1, per_page=10)

    recent_transactions = [
        TransactionResponse(
            id=txn.id,
            amount_usd=float(txn.amount_usd),
            transaction_type=txn.transaction_type,
            description=txn.description,
            balance_after=float(txn.balance_after) if txn.balance_after else None,
            created_at=txn.created_at,
        )
        for txn in txns_result["items"]
    ]

    return WalletResponse(
        balance=balance,
        recent_transactions=recent_transactions,
    )


@router.post(
    "/wallet/wire-order",
    status_code=status.HTTP_201_CREATED,
)
async def submit_wire_order(
    request: WireOrderRequest,
    db: Session = Depends(get_db),
    current: dict = Depends(require_admin),
):
    """
    Submit a wire transfer order to top up wallet.

    Validates minimum amount against platform settings (default 500,000 Tomans).
    """
    admin_id: int = current["id"]

    from app.services.billing.conversion import (
        get_min_topup_usd,
        get_platform_setting,
        get_toman_per_usd_rate,
        usd_to_tomans,
    )

    wire_service = WireOrderService(db)

    if request.payment_method == "crypto":
        address = get_platform_setting(db, "crypto_topup_address")
        if not address:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Crypto payments are not enabled",
            )
        amount_usd = Decimal(str(request.amount_usd))
        min_usd = get_min_topup_usd(db)
        if amount_usd < min_usd:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Minimum crypto top-up is ${float(min_usd):,.2f}",
            )
        rate = get_toman_per_usd_rate(db)
        amount_tomans = usd_to_tomans(amount_usd, rate)
        order = wire_service.create_order(
            admin_id=admin_id,
            amount_tomans=amount_tomans,
            contact_telegram=request.contact_telegram,
            contact_whatsapp=request.contact_whatsapp,
            contact_phone=request.contact_phone,
            notes=request.notes,
            payment_method="crypto",
            amount_usd=amount_usd,
            crypto_txid=request.crypto_txid,
            crypto_link=request.crypto_link,
            usd_rate_snapshot=rate,
        )
    else:
        min_setting = (
            db.query(PlatformSetting)
            .filter(PlatformSetting.key == "min_topup_tomans")
            .first()
        )
        min_tomans = Decimal(min_setting.value) if min_setting else Decimal("500000")
        amount_tomans = Decimal(str(request.amount_tomans))
        if amount_tomans < min_tomans:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Minimum wire order amount is {float(min_tomans):,.0f} Tomans",
            )
        order = wire_service.create_order(
            admin_id=admin_id,
            amount_tomans=amount_tomans,
            contact_telegram=request.contact_telegram,
            contact_whatsapp=request.contact_whatsapp,
            contact_phone=request.contact_phone,
            notes=request.notes,
        )

    return WireOrderResponse(
        id=order.id,
        amount_tomans=float(order.amount_tomans),
        amount_usd=float(order.amount_usd) if order.amount_usd else None,
        status=order.status,
        created_at=order.created_at,
    )


@router.get("/payment-config", response_model=PaymentConfigResponse)
async def get_payment_config(
    db: Session = Depends(get_db),
    current: dict = Depends(require_admin),
):
    """Payment config a reseller needs to render the crypto top-up screen.

    Exposes the super-admin-configured PLATFORM crypto address (for wallet
    top-ups) plus the conversion rate and minimum. `crypto_enabled` is False
    when no platform address is set (crypto option hidden client-side).
    """
    from app.services.billing.conversion import (
        get_min_topup_usd,
        get_platform_setting,
        get_toman_per_usd_rate,
    )

    address = get_platform_setting(db, "crypto_topup_address")
    return PaymentConfigResponse(
        crypto_enabled=bool(address),
        crypto_topup_address=address,
        crypto_topup_network=get_platform_setting(db, "crypto_topup_network"),
        crypto_topup_memo=get_platform_setting(db, "crypto_topup_memo"),
        min_topup_usd=float(get_min_topup_usd(db)),
        toman_per_usd_rate=float(get_toman_per_usd_rate(db)),
    )


@router.get("/panel-url", response_model=PanelUrlResponse)
async def get_panel_url(
    db: Session = Depends(get_db),
    current: dict = Depends(require_admin),
):
    """The calling reseller's own admin-panel URL, resolved per-reseller.

    Returns the effective admin_panel TLD (self-healing via TldSelectionService)
    or the platform default with is_fallback=True when no admin_panel TLD is
    active for this reseller.
    """
    url, domain, is_fallback = resolve_admin_panel_url(db, current["id"])
    return PanelUrlResponse(panel_url=url, domain=domain, is_fallback=is_fallback)


@router.get("/wallet/transactions")
async def get_wallet_transactions(
    transaction_type: str | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current: dict = Depends(require_admin),
):
    """
    Get paginated wallet transaction history for the authenticated admin.

    Filter by transaction_type.
    """
    admin_id: int = current["id"]

    wallet_service = WalletService(db)
    result = wallet_service.get_transactions(
        admin_id=admin_id,
        page=page,
        per_page=per_page,
        transaction_type=transaction_type,
    )

    items = [
        TransactionResponse(
            id=txn.id,
            amount_usd=float(txn.amount_usd),
            transaction_type=txn.transaction_type,
            description=txn.description,
            balance_after=float(txn.balance_after) if txn.balance_after else None,
            created_at=txn.created_at,
        )
        for txn in result["items"]
    ]

    return TransactionListResponse(
        items=items,
        total=result["total"],
        page=page,
        per_page=per_page,
    )


# ============================================================================
# ANALYTICS
# ============================================================================


@router.get("/analytics")
async def get_admin_analytics(
    db: Session = Depends(get_db),
    current: dict = Depends(RoleChecker(["admin", "super_admin"])),
):
    """
    Get per-admin analytics summary.

    Includes total/active users, total traffic (GB), total cost (USD),
    top 10 users by traffic, and protocol usage breakdown.
    All queries are scoped to this admin's data.
    """
    admin_id: int = current["id"]

    # User counts
    total_users = db.query(AdminUser).filter(AdminUser.admin_id == admin_id).count()
    active_users = (
        db.query(AdminUser)
        .filter(AdminUser.admin_id == admin_id, AdminUser.status == "active")
        .count()
    )

    # Total traffic (bytes to GB)
    traffic_result = (
        db.query(func.sum(TrafficLog.bytes_in) + func.sum(TrafficLog.bytes_out))
        .filter(TrafficLog.admin_id == admin_id)
        .scalar()
    )
    total_traffic_gb = (
        round(float(traffic_result) / BYTES_PER_GB, 2) if traffic_result else 0.0
    )

    # Total cost (sum of debit transactions in absolute value)
    from app.models.wallet_transaction_v2 import WalletTransactionV2

    cost_result = (
        db.query(func.sum(func.abs(WalletTransactionV2.amount_usd)))
        .filter(
            WalletTransactionV2.admin_id == admin_id,
            WalletTransactionV2.amount_usd < 0,
        )
        .scalar()
    )
    total_cost_usd = float(cost_result) if cost_result else 0.0

    # Top 10 users by traffic
    top_traffic = (
        db.query(
            AdminUser.username,
            func.sum(TrafficLog.bytes_in + TrafficLog.bytes_out).label("total_bytes"),
        )
        .join(TrafficLog, AdminUser.id == TrafficLog.user_id)
        .filter(AdminUser.admin_id == admin_id)
        .group_by(AdminUser.id, AdminUser.username)
        .order_by(desc("total_bytes"))
        .limit(10)
        .all()
    )

    top_users_by_traffic = [
        TopUserTraffic(
            username=row.username,
            traffic_gb=round(float(row.total_bytes) / BYTES_PER_GB, 4),
        )
        for row in top_traffic
        if row.total_bytes
    ]

    # Protocol usage breakdown (traffic in GB per protocol)
    protocol_traffic = (
        db.query(
            TrafficLog.protocol,
            func.sum(TrafficLog.bytes_in + TrafficLog.bytes_out).label("total_bytes"),
        )
        .filter(TrafficLog.admin_id == admin_id)
        .group_by(TrafficLog.protocol)
        .all()
    )

    protocol_breakdown = []
    for row in protocol_traffic:
        if not row.total_bytes:
            continue
        user_count = (
            db.query(func.count(func.distinct(TrafficLog.user_id)))
            .filter(
                TrafficLog.admin_id == admin_id,
                TrafficLog.protocol == row.protocol,
            )
            .scalar()
        ) or 0
        protocol_breakdown.append(
            ProtocolBreakdownEntry(
                protocol=row.protocol,
                traffic_gb=round(float(row.total_bytes) / BYTES_PER_GB, 2),
                user_count=user_count,
            )
        )

    return AdminAnalytics(
        total_users=total_users,
        active_users=active_users,
        total_traffic_gb=total_traffic_gb,
        total_cost_usd=total_cost_usd,
        top_users_by_traffic=top_users_by_traffic,
        protocol_breakdown=protocol_breakdown,
    )
