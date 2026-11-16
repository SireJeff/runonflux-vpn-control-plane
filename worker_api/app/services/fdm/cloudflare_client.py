"""
Cloudflare DNS API Client

Async HTTP client for managing DNS records on Cloudflare.
Supports CRUD operations for A records used by FluxVPN instances.

API Reference: https://developers.cloudflare.com/api/
SDK Reference: https://github.com/cloudflare/cloudflare-python
"""

import logging
from typing import Any, Dict, List, NoReturn, Optional

from cloudflare import AsyncCloudflare
from cloudflare.types.dns import RecordResponse

from .dns_provider import DnsProviderClient

logger = logging.getLogger(__name__)


# Cloudflare API Constants
DEFAULT_TTL = 120  # Cloudflare supports any TTL when not proxied
MIN_TTL = 60  # Minimum TTL for non-proxied records


class CloudflareDnsClientError(Exception):
    """Base exception for Cloudflare DNS client errors"""

    def __init__(self, message: str, status_code: Optional[int] = None):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


class CloudflareDnsClient(DnsProviderClient):
    """
    Async client for Cloudflare DNS API.

    Provides methods for managing DNS A records for a specific zone.
    Uses async context manager pattern for proper resource cleanup.

    Example:
        async with CloudflareDnsClient(
            api_token="your_token",
            zone_id="your_zone_id",
            domain="example.com"
        ) as client:
            records = await client.list_dns_records(record_type="A")
            await client.create_dns_record("us-01", "1.2.3.4")
    """

    def __init__(self, api_token: str, zone_id: str, domain: str):
        """
        Initialize the Cloudflare DNS client.

        Args:
            api_token: Cloudflare API token with DNS edit permissions
            zone_id: Cloudflare zone ID for the domain
            domain: The domain to manage DNS records for (e.g., "example.com")
        """
        self.api_token = api_token
        self.zone_id = zone_id
        self.domain = domain
        self._client: Optional[AsyncCloudflare] = None

    async def _get_client(self) -> AsyncCloudflare:
        """
        Get or create the Cloudflare async client.

        Returns:
            Configured AsyncCloudflare instance
        """
        if self._client is None:
            # Bound each call: the SDK defaults to a 60s timeout AND max_retries=2
            # with backoff, so a rate-limited/blackholed record can take ~3 min,
            # and the FDM sync calls this serially per-domain — enough to blow the
            # Celery 3600s hard limit and SIGKILL the whole sync. Cap timeout low
            # and drop retries so a bad call fails fast and the sync completes.
            self._client = AsyncCloudflare(
                api_token=self.api_token, timeout=10.0, max_retries=1
            )
        return self._client

    async def close(self):
        """Close the HTTP client connection."""
        if self._client:
            await self._client.close()
            self._client = None

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - ensures client is closed."""
        await self.close()

    def _fqdn(self, name: str) -> str:
        """Return the fully-qualified record name for the Cloudflare ``name=``
        list filter.

        FDM callers pass a bare subdomain label (``"us-01-a1"``) which must be
        qualified with the zone (``"us-01-a1.example.com"``). But the
        subscription/dashboard/admin_panel activation path passes the FULL apex
        domain (``name == self.domain``), and re-appending the zone there yields
        ``"example.com.example.com"`` — which matches nothing, so
        ``find_a_record_by_name`` misses the apex record and re-activation /
        deletion silently fail to update/remove it. Only append the zone when
        ``name`` is not already the apex or a subdomain of it.
        """
        if name == self.domain or name.endswith(f".{self.domain}"):
            return name
        return f"{name}.{self.domain}"

    def _validate_ttl(self, ttl: int) -> int:
        """
        Validate and normalize TTL value.

        Args:
            ttl: Time-to-live value in seconds

        Returns:
            Valid TTL value (minimum 60 seconds for non-proxied records)
        """
        if ttl < MIN_TTL:
            logger.warning(
                f"TTL value {ttl} below minimum {MIN_TTL}. "
                f"Using minimum TTL: {MIN_TTL}"
            )
            return MIN_TTL
        return ttl

    def _build_dns_record_payload(self, name: str, ip: str, ttl: int) -> Dict[str, Any]:
        """
        Build the DNS record payload for Cloudflare API.

        Args:
            name: Subdomain name (without domain, e.g., "us-01-a1")
            ip: IP address for the A record
            ttl: Time-to-live value in seconds

        Returns:
            Dictionary payload for API request
        """
        return {
            "type": "A",
            "name": name,
            "content": ip,
            "ttl": ttl,
            "proxied": False,  # Disable Cloudflare proxy for VPN connections
        }

    async def _handle_api_error(self, error: Exception, operation: str) -> NoReturn:
        """
        Handle API errors and convert to CloudflareDnsClientError.

        Args:
            error: The original exception
            operation: Description of the operation that failed

        Raises:
            CloudflareDnsClientError: Always raised with error details
        """
        error_msg = str(error)
        status_code = None

        # Try to extract status code from error
        if hasattr(error, "status_code"):
            status_code = error.status_code
        elif hasattr(error, "response") and hasattr(error.response, "status_code"):
            status_code = error.response.status_code

        logger.error(f"Cloudflare API error during {operation}: {error_msg}")
        raise CloudflareDnsClientError(
            f"Cloudflare API error: {error_msg}",
            status_code=status_code,
        ) from error

    def _require_record(
        self, record: Optional[RecordResponse], operation: str
    ) -> RecordResponse:
        """
        Ensure the SDK returned an actual DNS record and not None.

        The Cloudflare SDK types `get`/`create`/`update` responses as
        `Optional[RecordResponse]` -- the API can, in principle, return no
        record. Narrowing here turns an unguarded `None` (which would
        otherwise blow up as an AttributeError on first attribute access,
        still surfaced as a CloudflareDnsClientError by the `except Exception`
        handler in each caller) into an explicit, clearly-worded error of the
        same type.

        Args:
            record: The possibly-None record returned by the SDK
            operation: Description of the operation, for the error message

        Returns:
            The non-None record

        Raises:
            CloudflareDnsClientError: If record is None
        """
        if record is None:
            raise CloudflareDnsClientError(
                f"Cloudflare API returned no record for {operation}"
            )
        return record

    def _record_to_dict(self, record: RecordResponse) -> Dict[str, Any]:
        """
        Convert an SDK DNS record object into the dict shape used by callers.

        Args:
            record: A non-None Cloudflare DNS record response object

        Returns:
            Dictionary representation of the DNS record
        """
        return {
            "id": record.id,
            "type": record.type,
            "name": record.name,
            "content": record.content,
            "ttl": record.ttl,
            "proxied": record.proxied,
        }

    async def list_dns_records(
        self,
        record_type: Optional[str] = None,
        name: Optional[str] = None,
        per_page: int = 100,
    ) -> Dict[str, Any]:
        """
        List DNS records for the configured zone.

        Args:
            record_type: Filter by record type (e.g., "A", "CNAME", "TXT")
            name: Filter by record name
            per_page: Number of records per page (default: 100, max: 5000)

        Returns:
            Dictionary with DNS records data:
            {
                "data": [...],  # List of DNS records
                "result_info": {...}
            }

        Raises:
            CloudflareDnsClientError: On API errors
        """
        logger.debug(
            f"Listing DNS records for zone {self.zone_id} "
            f"(type={record_type}, name={name})"
        )

        try:
            client = await self._get_client()

            # Build filter parameters
            params = {"zone_id": self.zone_id, "per_page": min(per_page, 5000)}
            if record_type:
                params["type"] = record_type.upper()
            if name:
                params["name"] = self._fqdn(name)

            response = await client.dns.records.list(**params)  # type: ignore[arg-type]  # cloudflare stub: **kwargs splat over-constrained

            # Convert to dict format similar to ArvanCloud for compatibility
            records = []
            async for record in response:
                records.append(self._record_to_dict(record))

            return {"data": records}

        except Exception as e:
            await self._handle_api_error(e, "list_dns_records")

    async def get_dns_record(self, record_id: str) -> Dict[str, Any]:
        """
        Get a specific DNS record by ID.

        Args:
            record_id: The ID of the DNS record

        Returns:
            Dictionary with DNS record data

        Raises:
            CloudflareDnsClientError: On API errors
        """
        logger.debug(f"Getting DNS record {record_id} for zone {self.zone_id}")

        try:
            client = await self._get_client()
            record = await client.dns.records.get(
                zone_id=self.zone_id,
                dns_record_id=record_id,
            )
            record = self._require_record(record, f"get_dns_record({record_id})")

            return self._record_to_dict(record)

        except Exception as e:
            await self._handle_api_error(e, f"get_dns_record({record_id})")

    async def create_dns_record(
        self,
        name: str,
        ip: str,
        ttl: int = DEFAULT_TTL,
    ) -> Dict[str, Any]:
        """
        Create a new A record DNS entry.

        Args:
            name: Subdomain name (without domain, e.g., "us-01-a1")
            ip: IP address for the A record
            ttl: Time-to-live value in seconds (default: 120)

        Returns:
            Dictionary with created DNS record data

        Raises:
            CloudflareDnsClientError: On API errors
        """
        ttl = self._validate_ttl(ttl)

        logger.info(f"Creating DNS A record: {name}.{self.domain} -> {ip}")

        try:
            client = await self._get_client()
            record = await client.dns.records.create(
                zone_id=self.zone_id,
                type="A",
                name=name,
                content=ip,
                ttl=ttl,
                proxied=False,
            )
            record = self._require_record(record, f"create_dns_record({name})")

            return self._record_to_dict(record)

        except Exception as e:
            await self._handle_api_error(e, f"create_dns_record({name})")

    async def update_dns_record(
        self,
        record_id: str,
        name: str,
        ip: str,
        ttl: int = DEFAULT_TTL,
    ) -> Dict[str, Any]:
        """
        Update an existing DNS record.

        Args:
            record_id: The ID of the DNS record to update
            name: New subdomain name (without domain)
            ip: New IP address for the A record
            ttl: New time-to-live value in seconds

        Returns:
            Dictionary with updated DNS record data

        Raises:
            CloudflareDnsClientError: On API errors
        """
        ttl = self._validate_ttl(ttl)

        logger.info(f"Updating DNS record {record_id}: {name}.{self.domain} -> {ip}")

        try:
            client = await self._get_client()
            record = await client.dns.records.update(
                zone_id=self.zone_id,
                dns_record_id=record_id,
                type="A",
                name=name,
                content=ip,
                ttl=ttl,
                proxied=False,
            )
            record = self._require_record(record, f"update_dns_record({record_id})")

            return self._record_to_dict(record)

        except Exception as e:
            await self._handle_api_error(e, f"update_dns_record({record_id})")

    async def delete_dns_record(self, record_id: str) -> None:
        """
        Delete a DNS record.

        Args:
            record_id: The ID of the DNS record to delete

        Raises:
            CloudflareDnsClientError: On API errors
        """
        logger.info(f"Deleting DNS record {record_id} from zone {self.zone_id}")

        try:
            client = await self._get_client()
            await client.dns.records.delete(
                zone_id=self.zone_id,
                dns_record_id=record_id,
            )

        except Exception as e:
            await self._handle_api_error(e, f"delete_dns_record({record_id})")

    async def ensure_record_exists(
        self,
        name: str,
        ip: str,
        existing_record_id: Optional[str] = None,
        ttl: int = DEFAULT_TTL,
    ) -> Dict[str, Any]:
        """
        Create a new DNS record or update an existing one.

        This is a convenience method for idempotent DNS record management.
        If existing_record_id is provided, it updates that record.
        Otherwise, it creates a new record.

        Args:
            name: Subdomain name (without domain, e.g., "us-01-a1")
            ip: IP address for the A record
            existing_record_id: Optional ID of existing record to update
            ttl: Time-to-live value in seconds

        Returns:
            Dictionary with created/updated DNS record data

        Raises:
            CloudflareDnsClientError: On API errors
        """
        if existing_record_id:
            logger.debug(f"Updating existing DNS record {existing_record_id}")
            return await self.update_dns_record(existing_record_id, name, ip, ttl)

        # No existing record ID — try to create, but handle "identical record exists"
        try:
            logger.debug(f"Creating new DNS record for {name}")
            return await self.create_dns_record(name, ip, ttl)
        except CloudflareDnsClientError as e:
            if e.status_code == 400 and "81058" in str(e.message):
                logger.info(
                    f"DNS record already exists for {name}, looking up and updating"
                )
                existing = await self.find_a_record_by_name(name)
                if existing and existing.get("id"):
                    return await self.update_dns_record(existing["id"], name, ip, ttl)
            raise

    async def find_a_record_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Find an A record by its name.

        This is a convenience method that searches through A records
        to find one matching the given name.

        Args:
            name: Subdomain name to search for (without domain)

        Returns:
            Dictionary with DNS record data if found, None otherwise
        """
        try:
            response = await self.list_dns_records(
                record_type="A", name=name, per_page=100
            )
            records = response.get("data", [])

            # Return first matching record
            if records:
                return records[0]

            return None

        except CloudflareDnsClientError as e:
            logger.error(f"Error searching for A record '{name}': {e}")
            return None
