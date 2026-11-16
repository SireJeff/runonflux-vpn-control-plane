"""Protocol-specific usage adapters and dispatcher."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, cast

import httpx

from app.models import ProtocolInstance

logger = logging.getLogger(__name__)


@dataclass
class NormalizedUsageRecord:
    """Normalized usage payload consumed by usage tasks."""

    user_id: int
    bytes_uploaded: int
    bytes_downloaded: int
    connected_at: datetime
    disconnected_at: Optional[datetime] = None


class UsageAdapterError(Exception):
    """Raised when adapter cannot fetch/parse usage payload."""


class BaseUsageAdapter:
    """Base adapter for collecting instance usage from protocol runtime APIs."""

    protocol_keys: tuple[str, ...] = ()

    def collect(self, instance: ProtocolInstance) -> List[NormalizedUsageRecord]:
        payload = self.fetch_payload(instance)
        records = payload.get("records", []) if isinstance(payload, dict) else []
        if not isinstance(records, list):
            raise UsageAdapterError("Invalid usage payload: 'records' must be a list")
        return self.normalize_records(records)

    def fetch_payload(self, instance: ProtocolInstance) -> Dict[str, Any]:
        protocol = instance.protocol
        if protocol is None:
            raise UsageAdapterError("Instance is missing protocol relationship")

        import os

        telemetry_port = int(os.getenv("TELEMETRY_PORT", "9090"))

        url = f"http://{instance.ip_address}:{telemetry_port}/internal/usage"
        try:
            with httpx.Client(timeout=5.0) as client:
                response = client.get(url)
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    raise UsageAdapterError("Usage API returned non-object payload")
                return payload
        except Exception as exc:
            raise UsageAdapterError(f"Usage API fetch failed: {exc}") from exc

    def normalize_records(
        self, records: List[Dict[str, Any]]
    ) -> List[NormalizedUsageRecord]:
        normalized: List[NormalizedUsageRecord] = []
        for row in records:
            user_id = int(row["user_id"])
            bytes_uploaded = int(row.get("bytes_uploaded", 0))
            bytes_downloaded = int(row.get("bytes_downloaded", 0))
            connected_at = self._parse_datetime(row.get("connected_at"))
            disconnected_at = self._parse_datetime(
                row.get("disconnected_at"), required=False
            )

            normalized.append(
                NormalizedUsageRecord(
                    user_id=user_id,
                    bytes_uploaded=max(0, bytes_uploaded),
                    bytes_downloaded=max(0, bytes_downloaded),
                    connected_at=cast(datetime, connected_at),
                    disconnected_at=disconnected_at,
                )
            )
        return normalized

    @staticmethod
    def _parse_datetime(value: Any, required: bool = True) -> Optional[datetime]:
        if value in (None, ""):
            if required:
                raise UsageAdapterError("Missing required datetime value")
            return None

        if isinstance(value, datetime):
            return value

        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError as exc:
                raise UsageAdapterError(f"Invalid datetime format: {value}") from exc

        raise UsageAdapterError(f"Unsupported datetime value: {value}")


class SSHUsageAdapter(BaseUsageAdapter):
    protocol_keys = ("ssh",)

    def normalize_records(
        self, records: List[Dict[str, Any]]
    ) -> List[NormalizedUsageRecord]:
        mapped = []
        for row in records:
            mapped.append(
                {
                    "user_id": row.get("user_id"),
                    "bytes_uploaded": row.get(
                        "upload_bytes", row.get("bytes_uploaded", 0)
                    ),
                    "bytes_downloaded": row.get(
                        "download_bytes", row.get("bytes_downloaded", 0)
                    ),
                    "connected_at": row.get("connected_at"),
                    "disconnected_at": row.get("disconnected_at"),
                }
            )
        return super().normalize_records(mapped)


class ShadowsocksUsageAdapter(BaseUsageAdapter):
    protocol_keys = ("shadowsocks", "ss")

    def normalize_records(
        self, records: List[Dict[str, Any]]
    ) -> List[NormalizedUsageRecord]:
        mapped = []
        for row in records:
            mapped.append(
                {
                    "user_id": row.get("user_id"),
                    "bytes_uploaded": row.get("u", row.get("bytes_uploaded", 0)),
                    "bytes_downloaded": row.get("d", row.get("bytes_downloaded", 0)),
                    "connected_at": row.get("connected_at"),
                    "disconnected_at": row.get("disconnected_at"),
                }
            )
        return super().normalize_records(mapped)


class VLESSUsageAdapter(BaseUsageAdapter):
    protocol_keys = ("vless",)

    def normalize_records(
        self, records: List[Dict[str, Any]]
    ) -> List[NormalizedUsageRecord]:
        mapped = []
        for row in records:
            mapped.append(
                {
                    "user_id": row.get("user_id"),
                    "bytes_uploaded": row.get("uplink", row.get("bytes_uploaded", 0)),
                    "bytes_downloaded": row.get(
                        "downlink", row.get("bytes_downloaded", 0)
                    ),
                    "connected_at": row.get("connected_at"),
                    "disconnected_at": row.get("disconnected_at"),
                }
            )
        return super().normalize_records(mapped)


class TrojanUsageAdapter(BaseUsageAdapter):
    protocol_keys = ("trojan",)

    def normalize_records(
        self, records: List[Dict[str, Any]]
    ) -> List[NormalizedUsageRecord]:
        mapped = []
        for row in records:
            mapped.append(
                {
                    "user_id": row.get("user_id"),
                    "bytes_uploaded": row.get("sent", row.get("bytes_uploaded", 0)),
                    "bytes_downloaded": row.get(
                        "received", row.get("bytes_downloaded", 0)
                    ),
                    "connected_at": row.get("connected_at"),
                    "disconnected_at": row.get("disconnected_at"),
                }
            )
        return super().normalize_records(mapped)


class OutlineUsageAdapter(BaseUsageAdapter):
    protocol_keys = ("outline",)

    def normalize_records(
        self, records: List[Dict[str, Any]]
    ) -> List[NormalizedUsageRecord]:
        mapped = []
        for row in records:
            transferred = row.get("bytesTransferred", {})
            mapped.append(
                {
                    "user_id": row.get("user_id"),
                    "bytes_uploaded": transferred.get(
                        "upload", row.get("bytes_uploaded", 0)
                    ),
                    "bytes_downloaded": transferred.get(
                        "download", row.get("bytes_downloaded", 0)
                    ),
                    "connected_at": row.get("connected_at"),
                    "disconnected_at": row.get("disconnected_at"),
                }
            )
        return super().normalize_records(mapped)


class HTTPProxyUsageAdapter(BaseUsageAdapter):
    protocol_keys = ("http_proxy", "http-proxy", "http proxy", "http")

    def normalize_records(
        self, records: List[Dict[str, Any]]
    ) -> List[NormalizedUsageRecord]:
        mapped = []
        for row in records:
            mapped.append(
                {
                    "user_id": row.get("user_id"),
                    "bytes_uploaded": row.get("tx_bytes", row.get("bytes_uploaded", 0)),
                    "bytes_downloaded": row.get(
                        "rx_bytes", row.get("bytes_downloaded", 0)
                    ),
                    "connected_at": row.get("connected_at"),
                    "disconnected_at": row.get("disconnected_at"),
                }
            )
        return super().normalize_records(mapped)


ADAPTERS: List[BaseUsageAdapter] = [
    SSHUsageAdapter(),
    ShadowsocksUsageAdapter(),
    VLESSUsageAdapter(),
    TrojanUsageAdapter(),
    OutlineUsageAdapter(),
    HTTPProxyUsageAdapter(),
]


def resolve_usage_adapter(protocol_name: str) -> Optional[BaseUsageAdapter]:
    key = protocol_name.strip().lower()
    for adapter in ADAPTERS:
        if key in adapter.protocol_keys:
            return adapter
    return None
