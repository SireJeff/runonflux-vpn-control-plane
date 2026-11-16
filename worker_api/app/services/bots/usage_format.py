"""Human-readable remaining traffic + time for the subscription hero."""

from datetime import datetime, timezone

_GB = 1024 ** 3


def _bar(pct: float, width: int = 8) -> str:
    filled = max(0, min(width, round(pct / 100 * width)))
    return "█" * filled + "░" * (width - filled)


def format_remaining(traffic_limit_bytes, traffic_used_bytes, expires_at,
                     lang: str, now: datetime | None = None) -> str:
    used = (traffic_used_bytes or 0) / _GB
    if now is None:
        now = datetime.now(timezone.utc).replace(tzinfo=None)

    is_fa = (lang or "fa") == "fa"
    lines = []
    if traffic_limit_bytes is None:
        lines.append("📊 حجم: نامحدود" if is_fa else "📊 Data: Unlimited")
    else:
        limit = traffic_limit_bytes / _GB
        remaining = max(0.0, limit - used)
        pct = (used / limit * 100) if limit > 0 else 100.0
        if is_fa:
            lines.append(f"📊 مصرف: {used:.1f} / {limit:.0f} گیگ")
            lines.append(f"باقی‌مانده: {remaining:.1f} گیگ  {_bar(pct)} {pct:.0f}%")
        else:
            lines.append(f"📊 Usage: {used:.1f} / {limit:.0f} GB")
            lines.append(f"Remaining: {remaining:.1f} GB  {_bar(pct)} {pct:.0f}%")

    if expires_at is None:
        lines.append("🗓 انقضا: بدون انقضا" if is_fa else "🗓 Expiry: No expiry")
    else:
        days_left = max(0, (expires_at - now).days)
        if is_fa:
            lines.append(f"🗓 انقضا: {expires_at.date()} • {days_left} روز باقی‌مانده")
        else:
            lines.append(f"🗓 Expiry: {expires_at.date()} • {days_left} days left")
    return "\n".join(lines)
