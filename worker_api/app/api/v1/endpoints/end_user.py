"""
End User portal endpoints.

Provides authenticated end users with read-only access to their
connection strings, traffic usage, and profile information.
"""

import base64
import json
import logging
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.auth.password import set_password
from app.core.auth.role_dependencies import require_end_user
from app.core.constants import MACRO_REGIONS, country_flag, get_country_name
from app.core.crypto import decrypt_token
from app.core.database import get_db
from app.models.admin_users import AdminUser
from app.models.traffic_logs import TrafficLog
from app.models.user_regions import UserRegion
from app.schemas.end_user import (
    ConnectionStringsByCountry,
    ResetCredentialsResponse,
    UserConnectionsResponse,
    UserProfileResponse,
    UserUsageResponse,
)
from app.services.credentials.connection_string_service import (
    PROTOCOL_ORDER,
    ConnectionStringService,
    parse_ssh_fields,
)
from app.services.credentials.info_node import format_info_node_label, info_uri_line
from app.services.url_resolver import get_dashboard_base_url, get_subscription_base_url

# Protocols that have standardized URI schemes recognized by VPN clients
# (v2rayNG, v2box, NetMod). SSH and HTTP proxy have no standard URI scheme
# and are silently ignored or cause parse failures in subscription payloads.
SUBSCRIPTION_PROTOCOLS = {"ss", "vless", "trojan", "outline"}

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/user", tags=["End User"])


def _check_refresh_status(user) -> tuple:
    """Check if user can refresh. Returns (can_refresh, refresh_available_at)."""
    if not user.last_connection_refresh_at:
        return True, None
    refresh_at = user.last_connection_refresh_at + timedelta(hours=4)
    if datetime.now(timezone.utc).replace(tzinfo=None) >= refresh_at:
        return True, None
    return False, refresh_at


def _populate_parsed_fields(all_connections: dict) -> dict:
    """Add ``parsed_fields`` for SSH entries (mutates dict in-place).

    SSH URIs are RFC 3986 ``ssh://user:pass@host:port`` — clients like PuTTY
    and Termius need each field separately for form input. Other protocols
    have no equivalent field-wise representation, so they stay ``None`` and
    the frontend renders them as a single URI line.
    """
    for protocols in all_connections.values():
        for proto, data in protocols.items():
            if proto.lower() != "ssh":
                continue
            uri = data.get("primary") if isinstance(data, dict) else None
            if not uri:
                continue
            try:
                data["parsed_fields"] = parse_ssh_fields(uri)
            except ValueError:
                pass
    return all_connections


# Clients render used/total as a data bar; total=0 shows as "full". For
# unlimited users emit a large sentinel so the bar reads ~empty/unlimited.
_UNLIMITED_TOTAL_SENTINEL = 1099511627776000  # 1 PB in bytes


def _format_userinfo_total(traffic_limit_bytes):
    # Only NULL means unlimited -> large sentinel so the client bar reads ~empty.
    # A real 0 (0-GB / fully-blocked package) stays 0 (full bar), matching that
    # sync-users issues no credentials for such a user.
    if traffic_limit_bytes is None:
        return _UNLIMITED_TOTAL_SENTINEL
    return traffic_limit_bytes


def _header_safe_title(title: str) -> str:
    """Make a subscription Profile-Title safe for an HTTP header.

    HTTP headers must be latin-1 encodable, but display names are often non-ASCII
    (e.g. Persian). Sending such a name raw makes the ASGI server raise
    UnicodeEncodeError, 500-ing the whole subscription fetch. Non-latin-1 titles
    are carried via the widely-supported ``base64:`` prefix (sing-box, Hiddify,
    v2rayNG, Nekobox, ...); ASCII/latin-1 titles stay raw for universal client
    compatibility.
    """
    try:
        title.encode("latin-1")
        return title
    except UnicodeEncodeError:
        return "base64:" + base64.b64encode(title.encode("utf-8")).decode("ascii")


def _hero_fields(user, db: Session) -> dict:
    """Build {username, password, dashboard_url} for the response hero block.

    password is decrypted from password_enc (AES-GCM). Returns '' for users
    without enc storage (created before T1 migration) — they need to reset
    via the bot or POST /user/reset-credentials to populate password_enc.
    """
    password = ""
    if user.password_enc:
        try:
            password = decrypt_token(user.password_enc)
        except Exception:
            password = ""
    return {
        "username": user.username,
        "password": password,
        "dashboard_url": get_dashboard_base_url(db, user.admin_id) + "/user/login",
    }


# ---------------------------------------------------------------------------
# Subscription endpoint (unauthenticated — token IS the auth)
# ---------------------------------------------------------------------------


@router.get("/sub/{token}")
def get_subscription(
    token: str,
    format: str = Query("base64", description="Subscription format: base64 or singbox"),
    db: Session = Depends(get_db),
):
    """Subscription endpoint for VPN clients.

    Formats:
      - base64 (default): Base64-encoded URI lines for v2rayNG / v2box.
        Includes ss://, vless://, trojan:// (protocols with standard URI schemes).
      - singbox: JSON array of sing-box outbound configs for Throne / Hiddify.
        Includes ALL protocols: SSH, HTTP proxy, SS, VLESS, Trojan, Outline.

    No JWT required — the token in the URL identifies the user.
    """
    user = db.query(AdminUser).filter(AdminUser.subscription_token == token).first()
    if not user or user.status != "active":
        raise HTTPException(status_code=404, detail="Invalid subscription token")

    # Span EVERY macro-region the user actively holds, not just their primary.
    # `user.region` is a primary-only (is_primary==True) relationship, so using
    # it truncated all-region subscribers to their primary macro's countries.
    active_regions = (
        db.query(UserRegion)
        .filter(
            UserRegion.user_id == user.id,
            UserRegion.status == "active",
        )
        .all()
    )
    if not active_regions:
        raise HTTPException(status_code=404, detail="No region assigned")

    # Primary macro first, then the rest, de-duplicated — preserves ordering.
    active_macros = []
    for region in sorted(active_regions, key=lambda r: not r.is_primary):
        if region.macro_region not in active_macros:
            active_macros.append(region.macro_region)

    service = ConnectionStringService(db)

    # --- Common subscription headers ---
    traffic_used = user.traffic_used_bytes or 0
    traffic_total = _format_userinfo_total(user.traffic_limit_bytes)
    expire_ts = 0
    if user.expires_at:
        expire_ts = int(user.expires_at.timestamp())

    # Compact title suffix: remaining GB + days (ASCII only, header-safe).
    title_suffix = ""
    if user.traffic_limit_bytes is not None:
        rem_gb = max(0.0, (user.traffic_limit_bytes - (user.traffic_used_bytes or 0)) / (1024**3))
        title_suffix += f" | {rem_gb:.0f}GB left"
    if user.expires_at:
        days = max(0, (user.expires_at - datetime.utcnow()).days)
        title_suffix += f" | {days}d"

    # Header-safe once for both formats (non-ASCII display names would 500 the
    # response otherwise — HTTP headers are latin-1 only).
    profile_title = _header_safe_title(
        f"{user.display_name or user.username} - FluxVPN{title_suffix}"
    )

    # --- sing-box JSON format (all 6 protocols) ---
    if format.lower() == "singbox":
        _is_full, payload = service.generate_singbox_full_config(user)
        body = json.dumps(payload, ensure_ascii=False)
        response = Response(content=body, media_type="application/json")
        response.headers[
            "Subscription-Userinfo"
        ] = f"upload=0; download={traffic_used}; total={traffic_total}; expire={expire_ts}"
        response.headers["Profile-Update-Interval"] = "6"
        response.headers["Profile-Title"] = profile_title
        response.headers[
            "Content-Disposition"
        ] = f'attachment; filename="{user.username}_singbox.json"'
        return response

    # --- Default: Base64 URI format (ss://, vless://, trojan:// only) ---
    connections = service.generate_all_region_connections(user, increment_load=False)

    lines = []
    for macro_region in active_macros:
        for country_code in MACRO_REGIONS[macro_region]["countries"]:
            if country_code not in connections:
                continue
            country_protocols = connections[country_code]
            for protocol in PROTOCOL_ORDER:
                if protocol not in country_protocols:
                    continue
                if protocol not in SUBSCRIPTION_PROTOCOLS:
                    continue
                primary = country_protocols[protocol].get("primary")
                if primary:
                    lines.append(primary)

    info_label = format_info_node_label(
        user.traffic_limit_bytes,
        user.traffic_used_bytes,
        user.expires_at,
        getattr(user, "language", "fa") or "fa",
    )
    if info_label:
        lines.insert(0, info_uri_line(info_label))

    payload = "\n".join(lines)
    encoded = base64.b64encode(payload.encode("utf-8")).decode("utf-8")

    response = Response(content=encoded, media_type="text/plain")
    response.headers[
        "Subscription-Userinfo"
    ] = f"upload=0; download={traffic_used}; total={traffic_total}; expire={expire_ts}"
    response.headers["Profile-Update-Interval"] = "6"
    response.headers["Profile-Title"] = profile_title
    response.headers[
        "Content-Disposition"
    ] = f'attachment; filename="{user.username}_subscription.txt"'

    return response


@router.get("/connections", response_model=UserConnectionsResponse)
def get_connections(
    current_user: dict = Depends(require_end_user),
    db: Session = Depends(get_db),
):
    """Get all connection strings for the end user's macro region, grouped by country."""
    user = current_user["entity"]

    user_region = db.query(UserRegion).filter(UserRegion.user_id == user.id).first()
    macro_region = user_region.macro_region if user_region else None

    service = ConnectionStringService(db)
    all_connections = service.generate_all_region_connections(user)
    _populate_parsed_fields(all_connections)

    countries = []
    for country_code, protocols in all_connections.items():
        countries.append(
            ConnectionStringsByCountry(
                country_code=country_code,
                country_name=get_country_name(country_code),
                flag=country_flag(country_code),
                connections=protocols,
            )
        )

    can_refresh, refresh_available_at = _check_refresh_status(user)

    subscription_url = None
    if user.subscription_token:
        subscription_url = f"{get_subscription_base_url(db, user.admin_id)}/api/v1/user/sub/{user.subscription_token}"

    return UserConnectionsResponse(
        macro_region=macro_region,
        countries=countries,
        last_refreshed_at=user.last_connection_refresh_at,
        can_refresh=can_refresh,
        refresh_available_at=refresh_available_at,
        subscription_url=subscription_url,
        expires_at=user.expires_at.isoformat() if user.expires_at else None,
        **_hero_fields(user, db),
    )


@router.post("/refresh-connections", response_model=UserConnectionsResponse)
def refresh_connections(
    current_user: dict = Depends(require_end_user),
    db: Session = Depends(get_db),
):
    """Refresh connection strings. Rate-limited to once per 4 hours."""
    user = current_user["entity"]

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

    user_region = db.query(UserRegion).filter(UserRegion.user_id == user.id).first()
    macro_region = user_region.macro_region if user_region else None

    service = ConnectionStringService(db)
    all_connections = service.generate_all_region_connections(user)
    _populate_parsed_fields(all_connections)

    countries = []
    for country_code, protocols in all_connections.items():
        countries.append(
            ConnectionStringsByCountry(
                country_code=country_code,
                country_name=get_country_name(country_code),
                flag=country_flag(country_code),
                connections=protocols,
            )
        )

    can_refresh, refresh_available_at = _check_refresh_status(user)

    subscription_url = None
    if user.subscription_token:
        subscription_url = f"{get_subscription_base_url(db, user.admin_id)}/api/v1/user/sub/{user.subscription_token}"

    return UserConnectionsResponse(
        macro_region=macro_region,
        countries=countries,
        last_refreshed_at=user.last_connection_refresh_at,
        can_refresh=can_refresh,
        refresh_available_at=refresh_available_at,
        subscription_url=subscription_url,
        expires_at=user.expires_at.isoformat() if user.expires_at else None,
        **_hero_fields(user, db),
    )


@router.post("/reset-credentials", response_model=ResetCredentialsResponse)
def reset_credentials(
    current_user: dict = Depends(require_end_user),
    db: Session = Depends(get_db),
):
    """Rotate password and subscription token atomically.

    Mirrors the bot's reset_password_callback. Returns fresh creds so the
    user can re-copy them into their VPN client. The old sub URL stops
    working immediately (token changes); the old password stops working
    on the dashboard (hash changes).
    """
    user = current_user["entity"]

    new_pw = secrets.token_urlsafe(6)[:8]
    set_password(user, new_pw)
    user.subscription_token = secrets.token_hex(16)
    db.commit()
    db.refresh(user)

    return ResetCredentialsResponse(
        username=user.username,
        password=new_pw,
        subscription_url=(
            f"{get_subscription_base_url(db, user.admin_id)}/api/v1/user/sub/{user.subscription_token}"
        ),
        dashboard_url=get_dashboard_base_url(db, user.admin_id) + "/user/login",
    )


@router.get("/usage", response_model=UserUsageResponse)
def get_usage(
    current_user: dict = Depends(require_end_user),
    db: Session = Depends(get_db),
):
    """Get traffic consumption statistics for the end user.

    Returns total bytes/GB consumed, broken down by protocol and region.
    """
    user = current_user["entity"]

    # Total traffic
    total = (
        db.query(func.coalesce(func.sum(TrafficLog.bytes_in + TrafficLog.bytes_out), 0))
        .filter(TrafficLog.user_id == user.id)
        .scalar()
    )

    # Protocol breakdown
    protocol_stats = (
        db.query(
            TrafficLog.protocol,
            func.sum(TrafficLog.bytes_in + TrafficLog.bytes_out).label("bytes_total"),
        )
        .filter(TrafficLog.user_id == user.id)
        .group_by(TrafficLog.protocol)
        .all()
    )

    # Region breakdown
    region_stats = (
        db.query(
            TrafficLog.region_code,
            func.sum(TrafficLog.bytes_in + TrafficLog.bytes_out).label("bytes_total"),
        )
        .filter(TrafficLog.user_id == user.id)
        .group_by(TrafficLog.region_code)
        .all()
    )

    return UserUsageResponse(
        total_bytes=total,
        total_gb=round(total / 1073741824, 4),
        protocol_breakdown=[
            {
                "protocol": p,
                "bytes_total": b,
                "gb_total": round(b / 1073741824, 4),
            }
            for p, b in protocol_stats
        ],
        region_breakdown=[
            {
                "region_code": r,
                "bytes_total": b,
                "gb_total": round(b / 1073741824, 4),
            }
            for r, b in region_stats
        ],
    )


@router.get("/profile", response_model=UserProfileResponse)
def get_profile(
    current_user: dict = Depends(require_end_user),
    db: Session = Depends(get_db),
):
    """Get end user profile information."""
    user = current_user["entity"]

    user_region = db.query(UserRegion).filter(UserRegion.user_id == user.id).first()
    macro_region = user_region.macro_region if user_region else None

    subscription_url = None
    if user.subscription_token:
        subscription_url = f"{get_subscription_base_url(db, user.admin_id)}/api/v1/user/sub/{user.subscription_token}"

    return UserProfileResponse(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        remark=user.remark,
        status=user.status,
        macro_region=macro_region,
        subscription_url=subscription_url,
        expires_at=user.expires_at.isoformat() if user.expires_at else None,
    )
