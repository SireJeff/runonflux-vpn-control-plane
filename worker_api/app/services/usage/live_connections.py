"""Live connection telemetry adapters and resilience helpers."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple, cast

import httpx
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import ConnectionLog, ProtocolInstance

logger = logging.getLogger(__name__)


class LiveConnectionError(Exception):
    """Raised when live connection telemetry cannot be fetched or parsed."""


@dataclass
class LiveConnectionSample:
    user_id: int
    active_connections: int


class BaseLiveConnectionAdapter:
    protocol_keys: tuple[str, ...] = ()

    def collect(self, instance: ProtocolInstance) -> List[LiveConnectionSample]:
        payload = self.fetch_payload(instance)
        users = payload.get("users", []) if isinstance(payload, dict) else []
        if not isinstance(users, list):
            raise LiveConnectionError(
                "Invalid live connection payload: 'users' must be list"
            )
        return self.normalize_users(users)

    def fetch_payload(self, instance: ProtocolInstance) -> Dict[str, Any]:
        protocol = instance.protocol
        if protocol is None:
            raise LiveConnectionError("Instance is missing protocol relation")

        import os

        telemetry_port = int(os.getenv("TELEMETRY_PORT", "9090"))

        url = (
            f"http://{instance.ip_address}:{telemetry_port}/internal/active-connections"
        )
        try:
            with httpx.Client(timeout=5.0) as client:
                response = client.get(url)
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    raise LiveConnectionError(
                        "Live telemetry returned non-object payload"
                    )
                return payload
        except Exception as exc:
            raise LiveConnectionError(f"Live telemetry request failed: {exc}") from exc

    def normalize_users(
        self, users: List[Dict[str, Any]]
    ) -> List[LiveConnectionSample]:
        normalized: List[LiveConnectionSample] = []
        for row in users:
            user_id = int(row["user_id"])
            active = int(row.get("active_connections", 0))
            normalized.append(
                LiveConnectionSample(user_id=user_id, active_connections=max(0, active))
            )
        return normalized


class SSHLiveConnectionAdapter(BaseLiveConnectionAdapter):
    protocol_keys = ("ssh",)

    def normalize_users(
        self, users: List[Dict[str, Any]]
    ) -> List[LiveConnectionSample]:
        mapped = []
        for row in users:
            mapped.append(
                {
                    "user_id": row.get("user_id"),
                    "active_connections": row.get(
                        "sessions", row.get("active_connections", 0)
                    ),
                }
            )
        return super().normalize_users(mapped)


class ShadowsocksLiveConnectionAdapter(BaseLiveConnectionAdapter):
    protocol_keys = ("shadowsocks", "ss")

    def normalize_users(
        self, users: List[Dict[str, Any]]
    ) -> List[LiveConnectionSample]:
        mapped = []
        for row in users:
            mapped.append(
                {
                    "user_id": row.get("user_id"),
                    "active_connections": row.get(
                        "connections", row.get("active_connections", 0)
                    ),
                }
            )
        return super().normalize_users(mapped)


class VLESSLiveConnectionAdapter(BaseLiveConnectionAdapter):
    protocol_keys = ("vless",)


class TrojanLiveConnectionAdapter(BaseLiveConnectionAdapter):
    protocol_keys = ("trojan",)


class OutlineLiveConnectionAdapter(BaseLiveConnectionAdapter):
    protocol_keys = ("outline",)

    def normalize_users(
        self, users: List[Dict[str, Any]]
    ) -> List[LiveConnectionSample]:
        mapped = []
        for row in users:
            mapped.append(
                {
                    "user_id": row.get("user_id"),
                    "active_connections": row.get(
                        "numConnections", row.get("active_connections", 0)
                    ),
                }
            )
        return super().normalize_users(mapped)


class HTTPProxyLiveConnectionAdapter(BaseLiveConnectionAdapter):
    protocol_keys = ("http_proxy", "http-proxy", "http proxy", "http")


ADAPTERS: List[BaseLiveConnectionAdapter] = [
    SSHLiveConnectionAdapter(),
    ShadowsocksLiveConnectionAdapter(),
    VLESSLiveConnectionAdapter(),
    TrojanLiveConnectionAdapter(),
    OutlineLiveConnectionAdapter(),
    HTTPProxyLiveConnectionAdapter(),
]


def resolve_live_connection_adapter(
    protocol_name: str,
) -> Optional[BaseLiveConnectionAdapter]:
    key = protocol_name.strip().lower()
    for adapter in ADAPTERS:
        if key in adapter.protocol_keys:
            return adapter
    return None


def collect_live_connection_counts(
    instances: List[ProtocolInstance],
) -> Tuple[Dict[int, int], List[int], int]:
    """Collect active connection counts per user.

    Returns (user_totals, failed_instance_ids, telemetry_instance_count).
    """

    totals: Dict[int, int] = {}
    failed_instance_ids: List[int] = []
    telemetry_instance_count = 0

    for instance in instances:
        protocol_name = (
            (instance.protocol.slug if instance.protocol else None)
            or (instance.protocol.name if instance.protocol else None)
            or instance.component_name
            or ""
        )
        adapter = resolve_live_connection_adapter(cast(str, protocol_name))
        if not adapter:
            failed_instance_ids.append(cast(int, instance.id))
            continue

        try:
            samples = adapter.collect(instance)
            telemetry_instance_count += 1
            for sample in samples:
                totals[sample.user_id] = (
                    totals.get(sample.user_id, 0) + sample.active_connections
                )
        except LiveConnectionError as exc:
            logger.warning(
                "Live telemetry failed for instance %s: %s", instance.id, str(exc)
            )
            failed_instance_ids.append(cast(int, instance.id))

    return totals, failed_instance_ids, telemetry_instance_count


def fallback_connection_counts_from_logs(
    db: Session,
    instance_ids: List[int],
) -> Dict[int, int]:
    """Fallback heuristic for instances where telemetry failed."""

    if not instance_ids:
        return {}

    five_minutes_ago = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
        minutes=5
    )
    rows = (
        db.query(ConnectionLog.user_id, func.count(ConnectionLog.id).label("count"))
        .filter(
            ConnectionLog.instance_id.in_(instance_ids),
            ConnectionLog.connected_at >= five_minutes_ago,
            ConnectionLog.disconnected_at.is_(None),
        )
        .group_by(ConnectionLog.user_id)
        .all()
    )
    return {
        cast(int, row.user_id): cast(int, row.count)
        for row in rows
        if row.user_id is not None
    }
