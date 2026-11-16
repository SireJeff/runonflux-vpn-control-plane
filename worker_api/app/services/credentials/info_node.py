"""Display-only subscription 'info-node': shows remaining traffic + days as a
fake, non-connectable node at the top of the subscription list. Pure module."""

from datetime import datetime, timezone
from urllib.parse import quote

_GB = 1024 ** 3


def format_info_node_label(
    traffic_limit_bytes,
    traffic_used_bytes,
    expires_at,
    lang: str = "fa",
    now: datetime | None = None,
) -> str | None:
    """One-line status label, or None when there is nothing to report."""
    if traffic_limit_bytes is None and expires_at is None:
        return None
    if now is None:
        now = datetime.now(timezone.utc).replace(tzinfo=None)

    parts: list[str] = []
    if traffic_limit_bytes is None:
        parts.append("♾️")
    else:
        rem = max(0.0, (traffic_limit_bytes - (traffic_used_bytes or 0)) / _GB)
        # Integer GB when rem >= 1 or rem == 0; one decimal only for 0 < rem < 1.
        parts.append(f"{rem:.0f}GB" if (rem >= 1 or rem == 0) else f"{rem:.1f}GB")

    if expires_at is not None:
        days = max(0, (expires_at - now).days)
        parts.append(f"{days}d")

    suffix = "باقی‌مانده" if (lang or "fa") == "fa" else "left"
    return f"📊 {' · '.join(parts)} {suffix}"


def info_uri_line(label: str) -> str:
    """A syntactically valid, non-connectable trojan URI whose #fragment is the
    label. 127.0.0.1:1 never routes, so clients show it as an inert entry."""
    return (
        "trojan://info@127.0.0.1:1?security=tls&sni=127.0.0.1"
        f"#{quote(label, safe='')}"
    )


def info_singbox_outbound(label: str) -> dict:
    """A display-only sing-box outbound tagged with the label."""
    return {
        "type": "trojan",
        "tag": label,
        "server": "127.0.0.1",
        "server_port": 1,
        "password": "info",
        "tls": {"enabled": True, "server_name": "127.0.0.1", "insecure": True},
    }
