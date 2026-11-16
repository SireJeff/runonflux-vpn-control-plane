"""Resolve subscription/dashboard/admin-panel base URLs.

Per-admin resolution via TldSelectionService (multi-TLD feature), with a
legacy platform_settings / env fallback.

When ``admin_id`` is None the legacy path is used unchanged. When ``admin_id``
is given, resolution is per-admin and lazily persists an AdminTldState row on
first touch (a write-on-read); the concurrent first-touch race is handled in
TldSelectionService._store_assignment (SAVEPOINT + IntegrityError re-query).

Subscription and dashboard callers thread the owning ``user.admin_id``
(end_user.py, admin_api.py, orders/order_service.py, bots/end_user_connections.py).
The admin-panel surface is emitted per-reseller via resolve_admin_panel_url,
consumed by the GET /admin/panel-url endpoint.
"""

import logging

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.platform_settings import PlatformSetting
from app.services.tlds.selection import NoActiveTld, TldSelectionService

logger = logging.getLogger(__name__)


def _effective_domain(db: Session, admin_id: int | None, purpose: str) -> str | None:
    """Return 'https://{domain}' for the admin's effective TLD, else None.

    None on admin_id is None, no state yet, or empty pool (NoActiveTld).
    """
    if admin_id is None:
        return None
    try:
        tld = TldSelectionService(db).resolve_effective(admin_id, purpose)
    except NoActiveTld:
        logger.warning("No active TLD for purpose=%s; using legacy fallback", purpose)
        return None
    return f"https://{tld.domain}"


def get_subscription_base_url(db: Session, admin_id: int | None = None) -> str:
    effective = _effective_domain(db, admin_id, "subscription")
    if effective:
        return effective
    setting = (
        db.query(PlatformSetting)
        .filter(PlatformSetting.key == "subscription_base_url")
        .first()
    )
    if setting and setting.value:
        return setting.value
    return settings.FLUXVPN_API_URL


def get_dashboard_base_url(db: Session, admin_id: int | None = None) -> str:
    effective = _effective_domain(db, admin_id, "dashboard")
    if effective:
        return effective
    setting = (
        db.query(PlatformSetting)
        .filter(PlatformSetting.key == "dashboard_base_url")
        .first()
    )
    if setting and setting.value:
        return setting.value
    return settings.USER_PORTAL_URL


def resolve_admin_panel_url(db: Session, admin_id: int) -> tuple[str, str | None, bool]:
    """Return (url, domain_or_None, is_fallback) for a reseller's admin panel.

    - url: full 'https://…' URL, always present.
    - domain: effective admin_panel TLD host when one resolves, else None.
    - is_fallback: True when no effective admin_panel TLD (fell back to
      settings.USER_PORTAL_URL).
    """
    effective = _effective_domain(db, admin_id, "admin_panel")
    if effective:
        return effective, effective.removeprefix("https://"), False
    return settings.USER_PORTAL_URL, None, True


def get_api_base_url(db: Session) -> str:
    """Base URL where the FastAPI worker-api is publicly reachable (webhooks).

    Unchanged by the multi-TLD feature. Priority:
      1. platform_settings.api_base_url
      2. settings.FLUXVPN_API_URL
    """
    setting = (
        db.query(PlatformSetting).filter(PlatformSetting.key == "api_base_url").first()
    )
    if setting and setting.value:
        return setting.value
    return settings.FLUXVPN_API_URL
