import logging
from typing import Any, Dict, List, Optional
from urllib.parse import quote, urljoin

import httpx

from bot.config import get_config

logger = logging.getLogger(__name__)


class FluxVPNAPI:
    """Async HTTP client for the FluxVPN admin API."""

    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None
        self._tokens: Dict[int, str] = {}  # telegram_user_id -> JWT token

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            config = get_config()
            headers = {"Content-Type": "application/json"}
            if config.INTERNAL_API_KEY:
                headers["X-Internal-API-Key"] = config.INTERNAL_API_KEY
            self._client = httpx.AsyncClient(
                base_url=config.WORKER_API_URL,
                headers=headers,
                timeout=httpx.Timeout(config.API_TIMEOUT_WRITE),
            )
        return self._client

    def _headers(self, telegram_user_id: int) -> Dict[str, str]:
        token = self._tokens.get(telegram_user_id)
        if token:
            return {"Authorization": f"Bearer {token}"}
        return {}

    # --- Auth ---

    async def login(self, telegram_user_id: int, username: str, password: str) -> Optional[dict]:
        """Login and store token. Returns user info or None."""
        client = await self._get_client()
        try:
            resp = await client.post("/auth/login", json={"username": username, "password": password})
            if resp.status_code == 200:
                data = resp.json()
                self._tokens[telegram_user_id] = data["access_token"]
                return data
            return None
        except Exception as e:
            logger.error(f"Login failed: {e}")
            return None

    async def check_telegram_id(
        self, telegram_user_id: int, username: Optional[str] = None
    ) -> Optional[dict]:
        """Check if a telegram_id is linked to an admin account. Returns admin info or None.

        ``username`` is the caller's Telegram @username; the backend uses it only
        to self-heal admin rows whose telegram_id was mis-entered as a handle.
        """
        client = await self._get_client()
        try:
            path = f"/auth/check-telegram?telegram_id={telegram_user_id}"
            if username:
                path += f"&username={quote(username)}"
            resp = await client.get(path)
            if resp.status_code == 200:
                return resp.json()
            return None
        except Exception as e:
            logger.error(f"Telegram ID check failed: {e}")
            return None

    async def bot_login(
        self, telegram_user_id: int, username: Optional[str] = None
    ) -> Optional[dict]:
        """Authenticate via telegram_id (bot-to-backend). Stores JWT.

        ``username`` is forwarded so the backend can self-heal a handle-based
        telegram_id on the first authenticated contact.
        """
        client = await self._get_client()
        try:
            path = f"/auth/bot-login?telegram_id={telegram_user_id}"
            if username:
                path += f"&username={quote(username)}"
            resp = await client.post(path)
            if resp.status_code == 200:
                data = resp.json()
                self._tokens[telegram_user_id] = data["access_token"]
                return data
            return None
        except Exception as e:
            logger.error(f"Bot login failed: {e}")
            return None

    # --- Generic request helpers ---

    async def _get(self, path: str, telegram_user_id: int) -> Optional[dict]:
        client = await self._get_client()
        try:
            resp = await client.get(path, headers=self._headers(telegram_user_id))
            if resp.status_code == 200:
                return resp.json()
            logger.warning(f"GET {path} returned {resp.status_code}: {resp.text[:200]}")
            return None
        except Exception as e:
            logger.error(f"GET {path} failed: {e}")
            return None

    async def _post(self, path: str, telegram_user_id: int, data: dict = None) -> Optional[dict]:
        client = await self._get_client()
        try:
            resp = await client.post(path, json=data or {}, headers=self._headers(telegram_user_id))
            if resp.status_code in (200, 201):
                return resp.json()
            logger.warning(f"POST {path} returned {resp.status_code}: {resp.text[:200]}")
            return None
        except Exception as e:
            logger.error(f"POST {path} failed: {e}")
            return None

    async def _put(self, path: str, telegram_user_id: int, data: dict = None) -> Optional[dict]:
        client = await self._get_client()
        try:
            resp = await client.put(path, json=data or {}, headers=self._headers(telegram_user_id))
            if resp.status_code == 200:
                return resp.json()
            logger.warning(f"PUT {path} returned {resp.status_code}: {resp.text[:200]}")
            return None
        except Exception as e:
            logger.error(f"PUT {path} failed: {e}")
            return None

    async def _delete(self, path: str, telegram_user_id: int) -> bool:
        client = await self._get_client()
        try:
            resp = await client.delete(path, headers=self._headers(telegram_user_id))
            return resp.status_code in (200, 204)
        except Exception as e:
            logger.error(f"DELETE {path} failed: {e}")
            return False

    # --- Admin: Users ---

    async def list_users(self, telegram_user_id: int, page: int = 1, per_page: int = 5) -> Optional[dict]:
        return await self._get(f"/admin/users?page={page}&per_page={per_page}", telegram_user_id)

    async def get_user(self, telegram_user_id: int, user_id: int) -> Optional[dict]:
        return await self._get(f"/admin/users/{user_id}", telegram_user_id)

    async def toggle_user(self, telegram_user_id: int, user_id: int) -> Optional[dict]:
        return await self._post(f"/admin/users/{user_id}/toggle", telegram_user_id)

    # --- Admin: Wallet ---

    async def get_wallet(self, telegram_user_id: int) -> Optional[dict]:
        return await self._get("/admin/wallet", telegram_user_id)

    async def get_wallet_transactions(self, telegram_user_id: int, page: int = 1) -> Optional[dict]:
        return await self._get(f"/admin/wallet/transactions?page={page}&per_page=10", telegram_user_id)

    async def submit_wire_order(self, telegram_user_id: int, data: dict) -> Optional[dict]:
        return await self._post("/admin/wallet/wire-order", telegram_user_id, data)

    # --- Admin: Connections ---

    async def get_connections(self, telegram_user_id: int, user_id: int) -> Optional[dict]:
        return await self._get(f"/admin/users/{user_id}/connections", telegram_user_id)

    async def refresh_connections(self, telegram_user_id: int, user_id: int) -> Optional[dict]:
        return await self._post(f"/admin/users/{user_id}/refresh-connections", telegram_user_id)

    # --- Admin: Analytics ---

    async def get_analytics(self, telegram_user_id: int) -> Optional[dict]:
        return await self._get("/admin/analytics", telegram_user_id)

    # --- Super: Pending Admins ---

    async def list_pending_admins(self, telegram_user_id: int) -> Optional[List[dict]]:
        return await self._get("/super/admins/pending", telegram_user_id)

    async def approve_admin(self, telegram_user_id: int, admin_id: int, password: str) -> Optional[dict]:
        return await self._post(f"/super/admins/{admin_id}/approve", telegram_user_id, {"password": password})

    async def reject_admin(self, telegram_user_id: int, admin_id: int) -> Optional[dict]:
        return await self._delete(f"/super/admins/{admin_id}", telegram_user_id)

    # --- Super: Wire Orders ---

    async def list_wire_orders(self, telegram_user_id: int, status_filter: str = "pending") -> Optional[dict]:
        return await self._get(f"/super/orders?status={status_filter}", telegram_user_id)

    async def approve_wire_order(self, telegram_user_id: int, order_id: int, exchange_rate: float, admin_notes: str = "") -> Optional[dict]:
        return await self._post(f"/super/orders/{order_id}/approve", telegram_user_id, {
            "exchange_rate": exchange_rate,
            "admin_notes": admin_notes,
        })

    async def reject_wire_order(self, telegram_user_id: int, order_id: int, admin_notes: str = "") -> Optional[dict]:
        return await self._post(f"/super/orders/{order_id}/reject", telegram_user_id, {
            "admin_notes": admin_notes,
        })

    # --- Super: Analytics ---

    async def get_platform_analytics(self, telegram_user_id: int) -> Optional[dict]:
        return await self._get("/super/analytics", telegram_user_id)

    # --- Admin: Orders (End-User Receipts) ---

    async def list_orders(self, telegram_user_id: int, status: str = None) -> Optional[list]:
        """List end-user orders, optionally filtered by status (e.g. 'pending')."""
        path = "/admin/orders"
        if status:
            path += f"?status={status}"
        return await self._get(path, telegram_user_id)

    async def approve_order(self, telegram_user_id: int, order_id: int) -> Optional[dict]:
        """Approve a pending end-user order."""
        return await self._post(f"/admin/orders/{order_id}/approve", telegram_user_id)

    async def reject_order(self, telegram_user_id: int, order_id: int, reason: Optional[str] = None) -> Optional[dict]:
        """Reject a pending end-user order."""
        data = {"reason": reason} if reason else {}
        return await self._post(f"/admin/orders/{order_id}/reject", telegram_user_id, data)

    async def get_order_receipt_bytes(self, telegram_user_id: int, order_id: int) -> Optional[bytes]:
        """Fetch the receipt image for an order. Returns raw bytes or None."""
        client = await self._get_client()
        try:
            resp = await client.get(
                f"/admin/orders/{order_id}/receipt",
                headers=self._headers(telegram_user_id),
            )
            if resp.status_code == 200:
                return resp.content
            logger.warning(f"GET /admin/orders/{order_id}/receipt returned {resp.status_code}")
            return None
        except Exception as e:
            logger.error(f"GET /admin/orders/{order_id}/receipt failed: {e}")
            return None

    # --- Admin: Packages / Regions ---

    async def list_packages(self, telegram_user_id: int, include_inactive: bool = False) -> Optional[list]:
        path = "/admin/packages"
        if include_inactive:
            path += "?include_inactive=true"
        return await self._get(path, telegram_user_id)

    async def create_package(self, telegram_user_id: int, data: dict) -> Optional[dict]:
        return await self._post("/admin/packages", telegram_user_id, data)

    async def update_package(self, telegram_user_id: int, package_id: int, data: dict) -> Optional[dict]:
        return await self._put(f"/admin/packages/{package_id}", telegram_user_id, data)

    async def archive_package(self, telegram_user_id: int, package_id: int) -> bool:
        return await self._delete(f"/admin/packages/{package_id}", telegram_user_id)

    async def get_available_regions(self, telegram_user_id: int) -> Optional[list]:
        return await self._get("/admin/available-regions", telegram_user_id)

    async def renew_user(self, telegram_user_id: int, user_id: int, data: dict) -> Optional[dict]:
        return await self._post(f"/admin/users/{user_id}/renew", telegram_user_id, data)

    async def set_user_regions(self, telegram_user_id: int, user_id: int, macro_regions: list) -> Optional[dict]:
        return await self._put(
            f"/admin/users/{user_id}/regions", telegram_user_id, {"macro_regions": macro_regions}
        )

    # --- Cleanup ---

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()


# Singleton
_api: Optional[FluxVPNAPI] = None


def get_api() -> FluxVPNAPI:
    global _api
    if _api is None:
        _api = FluxVPNAPI()
    return _api
