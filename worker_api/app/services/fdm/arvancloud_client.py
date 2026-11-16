"""ArvanCloud DNS provider client implementing DnsProviderClient.

Uses ArvanCloud CDN API v4.0.
Base URL: https://napi.arvancloud.ir/cdn/4.0/domains/{domain}/dns-records
"""

import logging
import time
from typing import Any, Dict, Optional

import aiohttp
import redis

from app.core.config import settings
from app.core.redis_client import get_redis

from .dns_provider import DnsProviderClient

logger = logging.getLogger(__name__)

VALID_TTLS = [
    120,
    180,
    300,
    600,
    900,
    1800,
    3600,
    7200,
    18000,
    43200,
    86400,
    172800,
    432000,
]
DEFAULT_TTL = 120
DEFAULT_RATE_LIMIT_MAX_CALLS = 30  # shared across all Arvan FDM TLDs; see config.py
DEFAULT_RATE_LIMIT_WINDOW_SECONDS = 60


class ArvanCloudDnsClientError(Exception):
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class ArvanCloudRateLimitBudgetExceeded(ArvanCloudDnsClientError):
    """Raised when the local ArvanCloud call budget (Phase 4.4) is exhausted
    for the current window. Subclass of ArvanCloudDnsClientError so existing
    callers that catch the base type (super_admin.py's endpoint handlers,
    ensure_record_exists' own reconcile-by-name except) degrade safely
    without code changes.
    """


class ArvanCloudDnsClient(DnsProviderClient):
    """ArvanCloud DNS record management client using aiohttp."""

    BASE_URL = "https://napi.arvancloud.ir/cdn/4.0/domains"

    def __init__(self, api_key: str, domain: str):
        self.api_key = api_key
        self.domain = (
            domain  # Zone domain (e.g., "operator4.example.invalid"), used in API URL path
        )
        self._session: Optional[aiohttp.ClientSession] = None

    def _strip_zone(self, name: str) -> str:
        """Strip zone suffix from a full domain name to get the ArvanCloud record name.
        e.g. 'cdn.operator4.example.invalid' with zone 'operator4.example.invalid' → 'cdn'
        """
        zone_suffix = f".{self.domain}"
        if name.endswith(zone_suffix):
            return name[: -len(zone_suffix)]
        if name == self.domain:
            return "@"
        return name

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"ApiKey {self.api_key}",
            "Content-Type": "application/json",
        }

    def _url(self, path: str = "") -> str:
        return f"{self.BASE_URL}/{self.domain}/dns-records{path}"

    def _snap_ttl(self, ttl: int) -> int:
        if ttl in VALID_TTLS:
            return ttl
        closest = min(VALID_TTLS, key=lambda v: abs(v - ttl))
        logger.debug(f"TTL {ttl} snapped to {closest} (ArvanCloud restriction)")
        return closest

    # Hard per-request bound. aiohttp's default is a 300s total with no
    # connect bound, so a blackholed/slow ArvanCloud endpoint stalls the full
    # 300s per call; run serially across a domain pool that is enough to blow
    # the Celery 3600s hard limit and SIGKILL the whole FDM sync (freezing
    # every region). Cap each call so a bad endpoint fails fast and the sync
    # still completes. sock_connect catches SYN-blackholes; sock_read catches
    # accept-but-never-respond.
    _REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=15, sock_connect=5, sock_read=10)

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers=self._headers(), timeout=self._REQUEST_TIMEOUT
            )
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def _handle_error(self, response: aiohttp.ClientResponse, operation: str):
        if response.status >= 400:
            if response.status == 429:
                self._cap_current_window()
            body = await response.text()
            raise ArvanCloudDnsClientError(
                f"ArvanCloud API error during {operation}: {response.status} - {body[:500]}",
                status_code=response.status,
            )

    def _rate_limit_config(self) -> tuple:
        max_calls = getattr(
            settings, "FDM_ARVAN_RATE_LIMIT_MAX_CALLS", DEFAULT_RATE_LIMIT_MAX_CALLS
        )
        window_seconds = getattr(
            settings,
            "FDM_ARVAN_RATE_LIMIT_WINDOW_SECONDS",
            DEFAULT_RATE_LIMIT_WINDOW_SECONDS,
        )
        return max_calls, window_seconds

    async def _check_budget(self) -> None:
        """Enforce the ArvanCloud call budget (Phase 4.4).

        Fixed-window counter in Redis, shared across all FDM processes.
        Fail-open if Redis is unavailable -- a Redis blip must not block
        DNS convergence.
        """
        client = get_redis()
        if client is None:
            return

        max_calls, window_seconds = self._rate_limit_config()
        window_id = int(time.time() // window_seconds)
        key = f"fdm:ratelimit:arvancloud:{window_id}"

        try:
            count = client.incr(key)
            if count == 1:
                client.expire(key, window_seconds)
        except redis.RedisError as e:
            logger.warning(
                f"ArvanCloud rate-limit budget check failed ({e}); allowing call"
            )
            return

        if count > max_calls:
            raise ArvanCloudRateLimitBudgetExceeded(
                f"ArvanCloud call budget ({max_calls}/{window_seconds}s) exhausted"
            )

    def _cap_current_window(self) -> None:
        """On a real 429 from ArvanCloud, immediately cap the current
        window's budget counter so subsequent calls this window skip
        without probing further -- self-corrects even if the configured
        MAX_CALLS default is wrong for Arvan's actual limit.
        """
        client = get_redis()
        if client is None:
            return
        max_calls, window_seconds = self._rate_limit_config()
        window_id = int(time.time() // window_seconds)
        key = f"fdm:ratelimit:arvancloud:{window_id}"
        try:
            client.set(key, max_calls, ex=window_seconds)
        except redis.RedisError as e:
            logger.warning(f"ArvanCloud rate-limit reactive cap failed ({e}); ignoring")

    def _normalize_record(self, raw: Dict) -> Dict:
        value = raw.get("value", [])
        ip = ""
        if isinstance(value, list) and value:
            ip = value[0].get("ip", "") if isinstance(value[0], dict) else str(value[0])

        return {
            "id": raw.get("id", ""),
            "type": raw.get("type", "A").lower(),
            "name": raw.get("name", ""),
            "content": ip,
            "ttl": raw.get("ttl", DEFAULT_TTL),
            "proxied": raw.get("cloud", False),
        }

    async def list_dns_records(
        self,
        record_type: Optional[str] = None,
        name: Optional[str] = None,
        per_page: int = 100,
    ) -> Dict:
        await self._check_budget()
        session = await self._get_session()
        params: Dict[str, Any] = {"per_page": per_page}
        if record_type:
            params["type"] = record_type.lower()
        if name:
            params["search"] = name

        async with session.get(self._url(), params=params) as resp:
            await self._handle_error(resp, "list records")
            data = await resp.json()
            records = data.get("data", [])
            return {
                "result": [self._normalize_record(r) for r in records],
                "result_info": {"count": len(records)},
            }

    async def get_dns_record(self, record_id: str) -> Dict:
        await self._check_budget()
        session = await self._get_session()
        async with session.get(self._url(f"/{record_id}")) as resp:
            await self._handle_error(resp, "get record")
            data = await resp.json()
            return self._normalize_record(data.get("data", data))

    def _build_dns_record_payload(self, name: str, ip: str, ttl: int) -> Dict[str, Any]:
        """Build the ArvanCloud A-record create/update payload.

        Plain single-IP A record — deliberately NO load-balance fields
        (port/weight/country). ArvanCloud treats those keys as a load-balance
        record, which the Basic (free) plan rejects with HTTP 405 "load balance
        DNS records not allowed in Basic plan". FluxVPN load-balances at the
        assignment layer (TldSelectionService), never at DNS, so each record is
        a single-IP A record. See #388.
        """
        return {
            "type": "a",
            "name": self._strip_zone(name),
            "value": [{"ip": ip}],
            "ttl": self._snap_ttl(ttl),
            "cloud": False,
        }

    async def create_dns_record(
        self, name: str, ip: str, ttl: int = DEFAULT_TTL
    ) -> Dict:
        await self._check_budget()
        session = await self._get_session()
        payload = self._build_dns_record_payload(name, ip, ttl)
        async with session.post(self._url(), json=payload) as resp:
            await self._handle_error(resp, "create record")
            data = await resp.json()
            return self._normalize_record(data.get("data", data))

    async def update_dns_record(
        self, record_id: str, name: str, ip: str, ttl: int = DEFAULT_TTL
    ) -> Dict:
        await self._check_budget()
        session = await self._get_session()
        payload = self._build_dns_record_payload(name, ip, ttl)
        async with session.put(self._url(f"/{record_id}"), json=payload) as resp:
            await self._handle_error(resp, "update record")
            data = await resp.json()
            return self._normalize_record(data.get("data", data))

    async def delete_dns_record(self, record_id: str) -> None:
        await self._check_budget()
        session = await self._get_session()
        async with session.delete(self._url(f"/{record_id}")) as resp:
            await self._handle_error(resp, "delete record")

    async def ensure_record_exists(
        self,
        name: str,
        ip: str,
        existing_record_id: Optional[str] = None,
        ttl: int = DEFAULT_TTL,
    ) -> Dict:
        if existing_record_id:
            try:
                return await self.update_dns_record(existing_record_id, name, ip, ttl)
            except ArvanCloudRateLimitBudgetExceeded:
                raise
            except ArvanCloudDnsClientError:
                logger.warning(
                    f"Update failed for {name} (id={existing_record_id}), reconciling by name"
                )
        # No known record id (or update-by-id failed): reconcile by NAME before
        # creating. ArvanCloud rejects a same-name A-record create as "load
        # balance" on the Basic (free) plan, so if a record already exists for
        # this name whose id we lost (orphan: dns_record_id not persisted in our
        # DB), we must UPDATE it rather than POST a duplicate. The caller
        # persists record["id"], repairing the lost id -- so this is
        # self-healing, not just failure-avoidance. See #402.
        existing = await self.find_a_record_by_name(name)
        if existing and existing.get("id"):
            return await self.update_dns_record(existing["id"], name, ip, ttl)
        return await self.create_dns_record(name, ip, ttl)

    async def find_a_record_by_name(self, name: str) -> Optional[Dict]:
        # ArvanCloud stores/returns record names ZONE-STRIPPED ("@" for the apex,
        # "cdn" for cdn.<zone>), while callers pass either a bare label or the
        # FULL domain (the subscription/dashboard/admin_panel activation + delete
        # paths pass ``tld.domain``). Compare against the stripped form so the
        # apex record ("@") is actually found — otherwise re-activation and
        # deletion leave orphaned live A-records. See audit 2026-08-19.
        target = self._strip_zone(name)
        # Arvan's ``search`` is substring-based and won't match the apex "@"
        # sentinel, so for the apex scan unfiltered; otherwise search by label.
        search_name = None if target == "@" else target
        result = await self.list_dns_records(
            record_type="a", name=search_name, per_page=100
        )
        for record in result.get("result", []):
            if record.get("name") == target:
                return record
        return None
