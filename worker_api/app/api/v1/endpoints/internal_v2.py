"""
Internal API endpoints for VPN containers.

These endpoints are used by VPN protocol containers for:
- Reporting per-user traffic consumption
- Fetching user credentials for authentication
- Bulk syncing active users for periodic auth refresh

All endpoints require the X-Internal-API-Key header.
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import verify_internal_api_key
from app.models.admin_users import AdminUser
from app.models.user_credentials_v2 import UserCredentialV2
from app.schemas.end_user import (
    BulkSyncResponse,
    CredentialResponse,
    SyncedUser,
    TrafficReportRequest,
)
from app.services.billing.traffic_billing_service import TrafficBillingService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal", tags=["Internal"])


@router.post("/traffic-report")
def report_traffic(
    report: TrafficReportRequest,
    db: Session = Depends(get_db),
    _: bool = Depends(verify_internal_api_key),
):
    """Receive per-user traffic report from VPN containers.

    Processes the report: creates traffic log, updates user stats,
    calculates cost, deducts from admin wallet.

    Returns billing result with status, GB used, and cost.
    """
    service = TrafficBillingService(db)
    result = service.process_traffic_report(
        username=report.username,
        protocol=report.protocol,
        region_code=report.region,
        bytes_in=report.bytes_in,
        bytes_out=report.bytes_out,
        instance_ip=report.instance_ip,
        session_duration_seconds=report.session_duration_seconds,
        report_version=report.report_version,
        cumulative_in=report.cumulative_in,
        cumulative_out=report.cumulative_out,
        boot_id=report.boot_id,
        instance_id=report.instance_id,
    )

    if result.get("status") == "error":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=result.get("message", "User not found"),
        )

    return result


@router.get("/user-credentials", response_model=CredentialResponse)
def get_user_credentials(
    username: str,
    protocol: str,
    db: Session = Depends(get_db),
    _: bool = Depends(verify_internal_api_key),
):
    """Fetch credentials for a specific user and protocol.

    Used by VPN containers to authenticate users. The container
    calls this endpoint to retrieve the credential data needed
    to validate a user's connection attempt.
    """
    user = db.query(AdminUser).filter(AdminUser.username == username).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User '{username}' not found",
        )

    cred = (
        db.query(UserCredentialV2)
        .filter(
            UserCredentialV2.user_id == user.id,
            UserCredentialV2.protocol == protocol,
        )
        .first()
    )

    if not cred:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No credentials found for {username}/{protocol}",
        )

    return CredentialResponse(
        protocol=cred.protocol,
        credential_data=cred.credential_data,
    )


@router.get("/sync-users", response_model=BulkSyncResponse)
def sync_users(
    protocol: str,
    db: Session = Depends(get_db),
    _: bool = Depends(verify_internal_api_key),
):
    """Bulk-fetch all active users and their credentials for a protocol.

    Used by VPN containers for periodic auth sync. Returns only users
    with status='active' who have credentials for the requested protocol.

    Protocol name aliases are resolved automatically:
      - "ss" also matches "shadowsocks"
      - "shadowsocks" also matches "ss"
      - "http_proxy" also matches "http-proxy"
      - "http-proxy" also matches "http_proxy"
    """
    protocol_names = [protocol]
    aliases = {
        "ss": ["shadowsocks"],
        "shadowsocks": ["ss"],
        "http_proxy": ["http-proxy"],
        "http-proxy": ["http_proxy"],
    }
    protocol_names.extend(aliases.get(protocol, []))

    rows = (
        db.query(AdminUser.username, UserCredentialV2.credential_data)
        .join(UserCredentialV2, UserCredentialV2.user_id == AdminUser.id)
        .filter(
            AdminUser.status == "active",
            UserCredentialV2.protocol.in_(protocol_names),
            # Exclude users who exceeded their traffic limit
            # (NULL limit means unlimited)
            (
                (AdminUser.traffic_limit_bytes.is_(None))
                | (AdminUser.traffic_used_bytes < AdminUser.traffic_limit_bytes)
            ),
        )
        .order_by(AdminUser.id.asc())
        .all()
    )

    # Containers key Xray clients by email=username, compared case-insensitively;
    # a single duplicate makes Xray reject the whole config and crash-loops the
    # container fleet-wide. Keep the oldest row (rows are ordered by id) and
    # drop later duplicates loudly instead.
    users = []
    seen: set[str] = set()
    dropped: list[str] = []
    for row in rows:
        key = row.username.lower()
        if key in seen:
            dropped.append(row.username)
            continue
        seen.add(key)
        users.append(
            SyncedUser(username=row.username, credential_data=row.credential_data)
        )
    if dropped:
        logger.error(
            "sync-users(%s): dropped %d duplicate username(s) %s; fix the data, "
            "usernames must be globally unique",
            protocol,
            len(dropped),
            dropped,
        )

    logger.info("Synced %d users for protocol %s", len(users), protocol)

    return BulkSyncResponse(
        protocol=protocol,
        users=users,
        synced_at=datetime.now(timezone.utc),
    )
