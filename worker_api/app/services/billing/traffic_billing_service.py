import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.core.redis_client import get_redis
from app.models.admin_users import AdminUser
from app.models.admins import Admin
from app.models.platform_settings import PlatformSetting
from app.models.traffic_logs import TrafficLog
from app.services.notifications.router import NotificationRouter
from app.services.notifications.send_alert import send_telegram_alert
from app.services.notifications.templates import (
    format_traffic_exceeded,
    format_traffic_warning,
    format_user_suspended,
    format_wallet_depleted,
    format_wallet_low,
)
from app.services.notifications.templates_fa import (
    format_user_suspended_wallet_depleted,
    format_user_traffic_80,
    format_user_traffic_100,
)

from .wallet_service import WalletService

logger = logging.getLogger(__name__)


class TrafficBillingService:
    """Processes traffic reports and bills per GB against admin wallets."""

    def __init__(self, db: Session):
        self.db = db
        self.wallet_service = WalletService(db)

    # ------------------------------------------------------------------
    # Layer-1 anti-inflation guards
    # ------------------------------------------------------------------

    def _reject_inflated_report(
        self,
        user_id: int,
        protocol: str,
        instance_ip: str,
        bytes_in: int,
        bytes_out: int,
        total_bytes: int,
        session_duration_seconds: int,
    ):
        """Return a skip/reject result dict if this report is implausible or a
        frozen-cumulative repeat; return None to bill normally.

        Root cause (memory traffic_overbilling_rootcause_2026-07-25): a broken
        container delta-state re-sends the whole cumulative xray counter (or an
        identical value) every ~62s. The backend `+=` then over-bills N-fold.
        These two guards stop the unbounded case without a container redeploy;
        the full fix (backend-authoritative cumulative accounting) is Layer 2.
        """
        from app.core.config import settings

        # Guard A: plausibility ceiling. A single report cannot represent more
        # than (line-rate x window) bytes. Clamp a 60s floor on the window so a
        # tiny/zero session_duration can't shrink the ceiling absurdly.
        max_bps = int(getattr(settings, "TRAFFIC_MAX_BYTES_PER_SECOND", 131_072_000))
        window = max(int(session_duration_seconds or 0), 60)
        ceiling = max_bps * window
        if total_bytes > ceiling:
            logger.warning(
                "Rejecting implausible traffic report user=%s proto=%s ip=%s: "
                "%d bytes over %ds (> %d ceiling)",
                user_id,
                protocol,
                instance_ip,
                total_bytes,
                window,
                ceiling,
            )
            return {
                "status": "rejected_implausible",
                "bytes": total_bytes,
                "ceiling": ceiling,
            }

        # Guard B: frozen-repeat suppression. A broken container re-sends the
        # exact same (bytes_in, bytes_out) every cycle. Suppress an identical
        # consecutive report for the same (user, protocol, instance) within a
        # TTL window. Skip only non-trivial reports (tiny identical keepalives
        # legitimately repeat and are harmless). Never let Redis bookkeeping
        # errors block billing.
        dup_min = int(getattr(settings, "TRAFFIC_DUP_MIN_BYTES", 1_048_576))
        dup_ttl = int(getattr(settings, "TRAFFIC_DUP_TTL_SECONDS", 1_800))
        if total_bytes >= dup_min:
            redis = get_redis()
            if redis is not None:
                key = "traffic:last:%s:%s:%s" % (
                    user_id,
                    protocol,
                    instance_ip or "unknown",
                )
                current = "%d:%d" % (bytes_in, bytes_out)
                try:
                    prev = redis.get(key)
                    if prev is not None:
                        prev = prev.decode() if isinstance(prev, bytes) else prev
                    # Always (re)write with a fresh TTL so a stuck container
                    # stays suppressed and the key doesn't expire mid-freeze.
                    redis.setex(key, dup_ttl, current)
                    if prev == current:
                        logger.warning(
                            "Suppressing duplicate traffic report user=%s "
                            "proto=%s ip=%s bytes=%s",
                            user_id,
                            protocol,
                            instance_ip,
                            current,
                        )
                        return {"status": "skipped_duplicate", "bytes": total_bytes}
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "traffic dup-guard redis error user=%s: %s", user_id, exc
                    )

        return None

    # ------------------------------------------------------------------
    # Layer-2 authoritative cumulative accounting (v2)
    # ------------------------------------------------------------------

    def _apply_cumulative_report(
        self,
        user_id,
        protocol,
        instance_id,
        cumulative_in,
        cumulative_out,
        boot_id,
    ) -> int:
        """v2: compute the authoritative delta from the raw cumulative counter,
        update the per-(instance, boot_id) last-seen row, and return delta bytes.

        The row is keyed by boot_id as well as instance_id: one Flux app runs many
        replicas that all share the same instance_id but each generate a unique
        boot_id at start, so keying by boot_id gives each replica-boot its own row
        (no cross-replica collision). A replica restart => new boot_id => new row;
        first-sight bills that replica's small since-boot cumulative. Within a row
        (same boot_id), only an in-place counter dip below last-seen (e.g. xray
        restarted without the container restarting) resets a direction; otherwise
        the normal incremental delta applies.
        """
        from app.models.traffic_counters import TrafficCounter

        bid = boot_id or ""
        row = (
            self.db.query(TrafficCounter)
            .filter(
                TrafficCounter.user_id == user_id,
                TrafficCounter.protocol == protocol,
                TrafficCounter.instance_id == instance_id,
                TrafficCounter.boot_id == bid,
            )
            .first()
        )
        first_sight = row is None
        last_in = (row.last_cumulative_in or 0) if row is not None else 0
        last_out = (row.last_cumulative_out or 0) if row is not None else 0

        # Per-direction: on first sight (new replica-boot) bill the full cumulative;
        # otherwise bill full only for a direction that dipped below last-seen
        # (in-place reset), else the incremental delta.
        if first_sight or cumulative_in < last_in:
            delta_in = cumulative_in
        else:
            delta_in = cumulative_in - last_in
        if first_sight or cumulative_out < last_out:
            delta_out = cumulative_out
        else:
            delta_out = cumulative_out - last_out
        delta = max(0, delta_in) + max(0, delta_out)

        if row is None:
            row = TrafficCounter(
                user_id=user_id,
                protocol=protocol,
                instance_id=instance_id,
                boot_id=bid,
            )
            self.db.add(row)
        row.last_cumulative_in = cumulative_in
        row.last_cumulative_out = cumulative_out
        row.boot_id = bid
        return delta

    # ------------------------------------------------------------------
    # Alert helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _send_debounced_alert(
        redis_key: str, chat_id: int, message: str, ttl: int = 86400
    ) -> bool:
        """Send a Telegram alert only if no identical alert was sent within *ttl* seconds.

        Returns True if the alert was sent, False if suppressed or failed.
        """
        redis = get_redis()
        if not redis:
            return False
        if redis.exists(redis_key):
            return False
        redis.setex(redis_key, ttl, "1")
        return send_telegram_alert(chat_id, message)

    def _get_admin_telegram_id(self, admin_id: int):
        """Return the admin's telegram_id (as int) or None."""
        admin = self.db.query(Admin).filter(Admin.id == admin_id).first()
        if admin and admin.telegram_id:
            try:
                return int(admin.telegram_id)
            except (ValueError, TypeError):
                pass
        return None

    def _get_price_per_gb(self) -> Decimal:
        """Get current price per GB from platform settings."""
        setting = (
            self.db.query(PlatformSetting)
            .filter(PlatformSetting.key == "price_per_gb")
            .first()
        )
        return Decimal(setting.value) if setting else Decimal("0.02")

    def process_traffic_report(
        self,
        username: str,
        protocol: str,
        region_code: str,
        bytes_in: int,
        bytes_out: int,
        instance_ip: str,
        session_duration_seconds: int = 0,
        report_version: int = 1,
        cumulative_in: Optional[int] = None,
        cumulative_out: Optional[int] = None,
        boot_id: Optional[str] = None,
        instance_id: Optional[str] = None,
    ) -> dict:
        """Process a traffic report from a VPN container.

        1. Look up admin_users by username
        2. Create traffic_logs entry
        3. Update admin_users.traffic_used_bytes
        4. Calculate cost and deduct from admin wallet
        5. Check if wallet hit $0 -> trigger suspension

        Returns dict with status and details.
        """
        # Find user by username
        user = self.db.query(AdminUser).filter(AdminUser.username == username).first()
        if not user:
            return {"status": "error", "message": f"User '{username}' not found"}

        if user.status != "active":
            # v2: advance the per-instance last-seen baseline even while the user
            # is suspended, so bytes accumulated during suspension are NOT billed
            # as one lump on reactivation (esp. SSH, whose iptables counter never
            # resets). Do not bill.
            if (
                report_version >= 2
                and cumulative_in is not None
                and cumulative_out is not None
            ):
                inst = instance_id or instance_ip or "unknown"
                self._apply_cumulative_report(
                    user_id=user.id,
                    protocol=protocol,
                    instance_id=inst,
                    cumulative_in=cumulative_in,
                    cumulative_out=cumulative_out,
                    boot_id=boot_id,
                )
                self.db.commit()
            return {
                "status": "skipped",
                "message": f"User '{username}' is {user.status}",
            }

        if report_version >= 2:
            if cumulative_in is None or cumulative_out is None:
                return {
                    "status": "error",
                    "message": "v2 report missing cumulative_in/out",
                }
            inst = instance_id or instance_ip or "unknown"
            delta = self._apply_cumulative_report(
                user_id=user.id,
                protocol=protocol,
                instance_id=inst,
                cumulative_in=cumulative_in,
                cumulative_out=cumulative_out,
                boot_id=boot_id,
            )
            if delta <= 0:
                self.db.commit()  # persist the counter update even on zero delta
                return {
                    "status": "billed",
                    "user_id": user.id,
                    "gb_used": 0.0,
                    "cost_usd": 0.0,
                    "wallet_depleted": False,
                }
            # Plausibility CEILING backstop only. Do NOT reuse the Layer-1
            # dup-suppression here: a steady v2 delta legitimately repeats, and a
            # frozen v2 counter already yields delta=0 above.
            from app.core.config import settings

            _max_bps = int(
                getattr(settings, "TRAFFIC_MAX_BYTES_PER_SECOND", 131_072_000)
            )
            _window = max(int(session_duration_seconds or 0), 60)
            if delta > _max_bps * _window:
                self.db.commit()  # keep the counter advance; drop the implausible delta
                logger.warning(
                    "v2 implausible delta user=%s proto=%s inst=%s delta=%d (> %d)",
                    user.id,
                    protocol,
                    inst,
                    delta,
                    _max_bps * _window,
                )
                return {
                    "status": "rejected_implausible",
                    "bytes": delta,
                    "ceiling": _max_bps * _window,
                }
            # Represent the v2 delta as bytes_out for the shared log + billing path.
            bytes_in, bytes_out = 0, delta

        total_bytes = bytes_in + bytes_out
        if total_bytes <= 0:
            return {"status": "skipped", "message": "No traffic to bill"}

        # Layer-1 anti-inflation guards: reject implausible reports and suppress
        # frozen-cumulative repeats before they touch traffic_used_bytes.
        # v2 already applied its own ceiling backstop above; v1 keeps its
        # original dup-suppression + plausibility guard unchanged.
        if report_version < 2:
            guard_result = self._reject_inflated_report(
                user_id=user.id,
                protocol=protocol,
                instance_ip=instance_ip,
                bytes_in=bytes_in,
                bytes_out=bytes_out,
                total_bytes=total_bytes,
                session_duration_seconds=session_duration_seconds,
            )
            if guard_result is not None:
                return guard_result

        # Create traffic log
        log = TrafficLog(
            user_id=user.id,
            admin_id=user.admin_id,
            protocol=protocol,
            region_code=region_code,
            bytes_in=bytes_in,
            bytes_out=bytes_out,
            instance_ip=instance_ip,
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        self.db.add(log)

        # Update user's cumulative traffic (column default is 0)
        user.traffic_used_bytes = (user.traffic_used_bytes or 0) + total_bytes

        # --- Traffic alerts (80% / 100%) ---
        if user.traffic_limit_bytes and user.traffic_limit_bytes > 0:
            pct = (user.traffic_used_bytes / user.traffic_limit_bytes) * 100
            chat_id = self._get_admin_telegram_id(user.admin_id)
            if chat_id:
                if pct >= 100:
                    self._send_debounced_alert(
                        f"alert:traffic_100:{user.id}",
                        chat_id,
                        format_traffic_exceeded(
                            username=user.username,
                            used_gb=user.traffic_used_bytes / 1073741824,
                            limit_gb=user.traffic_limit_bytes / 1073741824,
                        ),
                    )
                elif pct >= 80:
                    self._send_debounced_alert(
                        f"alert:traffic_80:{user.id}",
                        chat_id,
                        format_traffic_warning(
                            username=user.username,
                            used_gb=user.traffic_used_bytes / 1073741824,
                            limit_gb=user.traffic_limit_bytes / 1073741824,
                            percentage=pct,
                        ),
                    )

            # --- End-user notification via reseller bot ---
            try:
                enduser_router = NotificationRouter(self.db)
                if pct >= 100:
                    enduser_router.send_to_end_user(
                        user.id,
                        format_user_traffic_100(),
                    )
                elif pct >= 80:
                    enduser_router.send_to_end_user(
                        user.id,
                        format_user_traffic_80(
                            used_gb=user.traffic_used_bytes / 1073741824,
                            limit_gb=user.traffic_limit_bytes / 1073741824,
                            pct=pct,
                        ),
                    )
            except Exception as exc:
                logger.warning(
                    f"End-user traffic alert failed for user {user.id}: {exc}"
                )

        # Calculate cost
        gb_used = Decimal(total_bytes) / Decimal(1073741824)  # 1024^3
        price_per_gb = self._get_price_per_gb()
        cost_usd = (gb_used * price_per_gb).quantize(Decimal("0.000001"))

        # Deduct from admin wallet
        self.wallet_service.debit_wallet(
            admin_id=user.admin_id,
            amount_usd=cost_usd,
            transaction_type="debit_traffic",
            user_id=user.id,
            description=f"Traffic: {gb_used:.4f} GB ({protocol}/{region_code}) for {username}",
        )

        # Check if wallet is depleted
        wallet_depleted = False
        if not self.wallet_service.has_positive_balance(user.admin_id):
            wallet_depleted = True
            self._suspend_admin_users(user.admin_id)

        # --- Wallet / suspension alerts ---
        chat_id = self._get_admin_telegram_id(user.admin_id)
        if chat_id:
            # Refresh admin object (wallet_service.debit_wallet commits internally)
            admin = self.db.query(Admin).filter(Admin.id == user.admin_id).first()
            if admin:
                if wallet_depleted:
                    # Wallet depleted alert
                    self._send_debounced_alert(
                        f"alert:wallet_depleted:{admin.id}",
                        chat_id,
                        format_wallet_depleted(),
                    )
                    # Individual suspended-user notifications
                    for suspended_user in (
                        self.db.query(AdminUser)
                        .filter(
                            AdminUser.admin_id == admin.id,
                            AdminUser.status == "suspended",
                        )
                        .all()
                    ):
                        send_telegram_alert(
                            chat_id,
                            format_user_suspended(
                                username=suspended_user.username,
                                reason="Admin wallet depleted",
                            ),
                        )
                elif (
                    admin.wallet_balance is not None
                    and 0 < float(admin.wallet_balance) < 2.0
                ):
                    # Low balance warning
                    self._send_debounced_alert(
                        f"alert:wallet_low:{admin.id}",
                        chat_id,
                        format_wallet_low(float(admin.wallet_balance)),
                    )

        self.db.commit()

        return {
            "status": "billed",
            "user_id": user.id,
            "gb_used": float(gb_used),
            "cost_usd": float(cost_usd),
            "wallet_depleted": wallet_depleted,
        }

    def _suspend_admin_users(self, admin_id: int):
        """Suspend all end users when admin wallet is depleted, then notify each."""
        users = (
            self.db.query(AdminUser)
            .filter(
                AdminUser.admin_id == admin_id,
                AdminUser.status == "active",
            )
            .all()
        )

        router = NotificationRouter(self.db)
        for user in users:
            user.status = "suspended"
            try:
                router.send_to_end_user(
                    user.id,
                    format_user_suspended_wallet_depleted(),
                )
            except Exception as exc:
                logger.warning(f"Failed to notify user {user.id} of suspension: {exc}")

        self.db.commit()
        logger.warning(
            f"Suspended {len(users)} users for admin {admin_id} (wallet depleted)"
        )
