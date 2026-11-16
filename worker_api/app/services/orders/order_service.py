"""End-user order lifecycle: create, review (approve/reject), referral, delivery.

Task 9B: create_order and reject_order.
Task 9D: approve_order, _maybe_award_referral, _deliver_connections.
"""

import logging
import secrets
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.core.auth.password import set_password
from app.core.constants import MACRO_REGIONS, country_flag, get_country_name
from app.models.admin_bots import AdminBot
from app.models.admin_packages import AdminPackage
from app.models.admin_referral import AdminReferralConfig, AdminReferralEarning
from app.models.admin_users import AdminUser
from app.models.free_config_enrollment import FreeConfigEnrollment
from app.models.user_credentials_v2 import UserCredentialV2
from app.models.user_orders import UserOrder
from app.services.billing.user_wallet_ledger import record_wallet_txn
from app.services.credentials.connection_string_service import ConnectionStringService
from app.services.credentials.reseller_credential_service import CredentialService
from app.services.notifications.router import NotificationRouter
from app.services.notifications.templates_fa import template_for
from app.services.referral.codes import ensure_referral_code
from app.services.regions.assignment import set_user_regions
from app.services.subscriptions.renewal_service import compute_new_expiry
from app.services.url_resolver import get_dashboard_base_url, get_subscription_base_url

logger = logging.getLogger(__name__)


class OrderError(Exception):
    """Raised when an order operation cannot be completed."""


class OrderService:
    def __init__(self, db: Session):
        self.db = db
        self.router = NotificationRouter(db)

    def create_order(
        self,
        user: AdminUser,
        package_id: int,
        macro_region: str | None = None,
        macro_regions: list[str] | None = None,
        wallet_credit_to_apply_tomans: Decimal = Decimal("0"),
        receipt_file_id: Optional[str] = None,
        receipt_file_unique_id: Optional[str] = None,
        payment_method: str = "card",
        crypto_txid: Optional[str] = None,
        crypto_link: Optional[str] = None,
    ) -> UserOrder:
        """Create a pending order for a user.

        Validates:
        - Package exists, belongs to user.admin_id, is_active=True
        - Every entry in the macro_region set is a valid MACRO_REGIONS key (eu/as/na/row)
        - wallet credit applied is capped at user's current balance

        Side effects:
        - Debits user.wallet_credit_tomans immediately (refundable on rejection)
        - Sets user.current_order_id after order is persisted
        """
        regions = macro_regions or ([macro_region] if macro_region else [])
        regions = list(dict.fromkeys(r for r in regions if r))
        if not regions:
            raise OrderError("At least one macro_region is required")
        primary_region = regions[0]

        pkg = (
            self.db.query(AdminPackage)
            .filter(
                AdminPackage.id == package_id,
                AdminPackage.admin_id == user.admin_id,
                AdminPackage.is_active == True,  # noqa: E712
            )
            .first()
        )
        if not pkg:
            raise OrderError("Package not found or inactive")

        for r in regions:
            if r not in MACRO_REGIONS:
                raise OrderError(f"Invalid macro_region: {r}")

        user_balance = user.wallet_credit_tomans or Decimal("0")
        applied = min(wallet_credit_to_apply_tomans, user_balance)
        amount_due = pkg.price_tomans - applied

        amount_usd_snapshot = None
        if payment_method == "crypto":
            bot = (
                self.db.query(AdminBot)
                .filter(AdminBot.admin_id == user.admin_id)
                .first()
            )
            if not bot or not bot.crypto_address:
                raise OrderError("Crypto payments are not enabled for this reseller")

            from app.services.billing.conversion import (
                get_toman_per_usd_rate,
                tomans_to_usd,
            )

            amount_usd_snapshot = tomans_to_usd(
                amount_due, get_toman_per_usd_rate(self.db)
            )

        snapshot = {
            "name": pkg.name,
            "traffic_gb": float(pkg.traffic_limit_gb),
            "duration_days": pkg.duration_days,
            "price_tomans": float(pkg.price_tomans),
        }

        order = UserOrder(
            user_id=user.id,
            admin_id=user.admin_id,
            package_id=pkg.id,
            package_snapshot=snapshot,
            macro_region=primary_region,
            macro_regions=regions,
            amount_tomans=amount_due,
            wallet_credit_applied_tomans=applied,
            status="pending",
            receipt_file_id=receipt_file_id,
            receipt_file_unique_id=receipt_file_unique_id,
            payment_method=payment_method,
            crypto_txid=crypto_txid,
            crypto_link=crypto_link,
            amount_usd_snapshot=amount_usd_snapshot,
            expires_at=datetime.now(timezone.utc).replace(tzinfo=None)
            + timedelta(hours=72),
        )
        self.db.add(order)

        self.db.commit()
        self.db.refresh(order)

        if applied > 0:
            record_wallet_txn(self.db, user, -applied, "spend", order.id)

        user.current_order_id = order.id
        self.db.commit()

        return order

    def create_topup_order(
        self,
        user: AdminUser,
        amount_tomans: Decimal,
        receipt_file_id: Optional[str] = None,
        receipt_file_unique_id: Optional[str] = None,
        payment_method: str = "card",
        crypto_txid: Optional[str] = None,
        crypto_link: Optional[str] = None,
    ) -> UserOrder:
        """Create a pending wallet top-up order (kind='topup')."""
        if amount_tomans <= 0:
            raise OrderError("Top-up amount must be positive")

        amount_usd_snapshot = None
        if payment_method == "crypto":
            bot = (
                self.db.query(AdminBot)
                .filter(AdminBot.admin_id == user.admin_id)
                .first()
            )
            if not bot or not bot.crypto_address:
                raise OrderError("Crypto payments are not enabled for this reseller")
            from app.services.billing.conversion import (
                get_toman_per_usd_rate,
                tomans_to_usd,
            )

            amount_usd_snapshot = tomans_to_usd(
                amount_tomans, get_toman_per_usd_rate(self.db)
            )

        order = UserOrder(
            user_id=user.id,
            admin_id=user.admin_id,
            kind="topup",
            package_id=None,
            package_snapshot=None,
            macro_region=None,
            macro_regions=None,
            amount_tomans=amount_tomans,
            wallet_credit_applied_tomans=Decimal("0"),
            status="pending",
            receipt_file_id=receipt_file_id,
            receipt_file_unique_id=receipt_file_unique_id,
            payment_method=payment_method,
            crypto_txid=crypto_txid,
            crypto_link=crypto_link,
            amount_usd_snapshot=amount_usd_snapshot,
            expires_at=datetime.now(timezone.utc).replace(tzinfo=None)
            + timedelta(hours=72),
        )
        self.db.add(order)
        self.db.commit()
        self.db.refresh(order)
        return order

    def reject_order(
        self,
        order_id: int,
        reviewer_admin_id: int,
        reason: Optional[str] = None,
    ) -> UserOrder:
        """Reject a pending order: refund applied wallet credit, notify user."""
        order = (
            self.db.query(UserOrder)
            .filter(
                UserOrder.id == order_id,
                UserOrder.admin_id == reviewer_admin_id,
            )
            .first()
        )
        if not order:
            raise OrderError("Order not found")
        if order.status != "pending":
            raise OrderError(f"Order is {order.status}, not pending")

        user = self.db.query(AdminUser).filter(AdminUser.id == order.user_id).first()

        if order.wallet_credit_applied_tomans > 0 and user:
            record_wallet_txn(
                self.db, user, order.wallet_credit_applied_tomans, "refund", order.id
            )

        order.status = "rejected"
        order.reviewer_admin_id = reviewer_admin_id
        order.reviewed_at = datetime.now(timezone.utc).replace(tzinfo=None)
        order.rejection_reason = reason

        self.db.commit()
        self.db.refresh(order)

        if user:
            tpl = template_for(getattr(user, "language", "fa"))
            msg = tpl.format_user_order_rejected(order.id, reason)
            self.router.send_to_end_user(user.id, msg)

        return order

    def approve_order(self, order_id: int, reviewer_admin_id: int) -> UserOrder:
        """Approve a pending order: activate user, generate creds, deliver.

        Steps:
        1. Validate order exists, belongs to this admin, status=pending
        2. Activate user (additive expires_at, traffic_limit_bytes, status='active')
        3. Reconcile UserRegion rows to order.macro_regions (full set) via set_user_regions
        4. Generate credentials if first purchase (no existing UserCredentialV2 rows)
        5. Mark order approved
        6. Award referral commission to referrer if applicable
        7. Send connection strings to end-user via reseller bot
        """
        order = (
            self.db.query(UserOrder)
            .filter(
                UserOrder.id == order_id,
                UserOrder.admin_id == reviewer_admin_id,
            )
            .first()
        )
        if not order:
            raise OrderError("Order not found")
        if order.status != "pending":
            raise OrderError(f"Order is {order.status}, not pending")

        user = self.db.query(AdminUser).filter(AdminUser.id == order.user_id).first()
        if not user:
            raise OrderError("User not found")

        if order.kind == "topup":
            record_wallet_txn(self.db, user, order.amount_tomans, "topup", order.id)
            order.status = "approved"
            order.reviewer_admin_id = reviewer_admin_id
            order.reviewed_at = datetime.now(timezone.utc).replace(tzinfo=None)
            self.db.commit()
            self.db.refresh(order)
            self.db.refresh(user)
            tpl = template_for(getattr(user, "language", "fa"))
            self.router.send_to_end_user(
                user.id,
                tpl.format_wallet_topup_approved(
                    order.amount_tomans, user.wallet_credit_tomans
                ),
            )
            return order

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        self._activate_subscription(order, user, now)

        order.status = "approved"
        order.reviewer_admin_id = reviewer_admin_id
        order.reviewed_at = datetime.now(timezone.utc).replace(tzinfo=None)

        self.db.commit()
        self.db.refresh(order)
        self.db.refresh(user)

        self._maybe_award_referral(user, order)
        self._deliver_connections(user)

        return order

    def create_wallet_paid_order(
        self, user: AdminUser, package_id: int, macro_regions: list[str]
    ) -> UserOrder:
        """Create an already-approved subscription order paid fully from wallet.

        Activates immediately — no receipt, no admin approval.
        """
        regions = list(dict.fromkeys(r for r in (macro_regions or []) if r))
        if not regions:
            raise OrderError("At least one macro_region is required")

        pkg = (
            self.db.query(AdminPackage)
            .filter(
                AdminPackage.id == package_id,
                AdminPackage.admin_id == user.admin_id,
                AdminPackage.is_active == True,  # noqa: E712
            )
            .first()
        )
        if not pkg:
            raise OrderError("Package not found or inactive")

        for r in regions:
            if r not in MACRO_REGIONS:
                raise OrderError(f"Invalid macro_region: {r}")

        # Serialize the whole spend under the user row lock so a concurrent
        # second tap blocks here until the first commits, then reads the
        # reduced balance and is rejected cleanly before any order is created.
        # (On SQLite with_for_update() is a no-op; that's expected.)
        locked_user = (
            self.db.query(AdminUser)
            .filter(AdminUser.id == user.id)
            .with_for_update()
            .first()
        )
        if not locked_user:
            raise OrderError("User not found")

        balance = locked_user.wallet_credit_tomans or Decimal("0")
        if balance < pkg.price_tomans:
            raise OrderError("Insufficient wallet balance")

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        snapshot = {
            "name": pkg.name,
            "traffic_gb": float(pkg.traffic_limit_gb),
            "duration_days": pkg.duration_days,
            "price_tomans": float(pkg.price_tomans),
        }
        order = UserOrder(
            user_id=locked_user.id,
            admin_id=locked_user.admin_id,
            kind="subscription",
            package_id=pkg.id,
            package_snapshot=snapshot,
            macro_region=regions[0],
            macro_regions=regions,
            amount_tomans=Decimal("0"),
            wallet_credit_applied_tomans=pkg.price_tomans,
            status="approved",
            payment_method="wallet",
            reviewer_admin_id=locked_user.admin_id,
            reviewed_at=now,
        )
        # Do NOT commit an approved order before the debit succeeds. Add the
        # order (uncommitted), debit, activate, then a SINGLE commit — if the
        # debit or activation raises, nothing commits and no approved order
        # can leak.
        self.db.add(order)
        self.db.flush()  # assign order.id without committing

        record_wallet_txn(self.db, locked_user, -pkg.price_tomans, "spend", order.id)
        locked_user.current_order_id = order.id
        self._activate_subscription(order, locked_user, now)
        self.db.commit()
        self.db.refresh(order)
        self.db.refresh(locked_user)
        user = locked_user

        self._maybe_award_referral(user, order)
        self._deliver_connections(user)
        return order

    def _activate_subscription(
        self, order: UserOrder, user: AdminUser, now: datetime
    ) -> None:
        """Activate a subscription order: expiry, traffic, regions, creds, ref code."""
        # SQLAlchemy legacy Column[Any] typing false positive: package_snapshot
        # is a JSON column and is a real dict at runtime; mypy sees
        # "Column[Any] | dict[Never, Never]" from the class descriptor, not
        # the instance value.
        snapshot: Dict[str, Any] = order.package_snapshot or {}  # type: ignore[assignment]
        duration_days = int(snapshot.get("duration_days", 30))
        traffic_gb = float(snapshot.get("traffic_gb", 0))

        user.expires_at = compute_new_expiry(user.expires_at, duration_days, now)
        user.traffic_limit_bytes = int(traffic_gb * 1024**3)
        user.traffic_used_bytes = 0
        user.status = "active"

        regions = order.macro_regions or (
            [order.macro_region] if order.macro_region else []
        )
        from app.services.regions.availability import healthy_macro_codes

        healthy = healthy_macro_codes(self.db)
        filtered = [r for r in regions if r in healthy]
        dropped = [r for r in regions if r not in healthy]
        if dropped:
            logger.warning(
                "activate: order %s (user %s) requested unhealthy regions %s; provisioning %s",
                order.id,
                user.id,
                dropped,
                filtered or regions,
            )
        # Floor: never leave a paid order region-less. If EVERY requested region is
        # currently unhealthy, provision the original set anyway (FDM sync self-heals
        # as capacity returns) rather than stranding the user with no UserRegion rows.
        set_user_regions(self.db, user, filtered or regions, now)

        existing_creds = (
            self.db.query(UserCredentialV2).filter_by(user_id=user.id).count()
        )
        if existing_creds == 0:
            CredentialService(self.db).generate_user_credentials(user)

        # Assign referral code if user doesn't have one yet
        ensure_referral_code(user)

        # Buying a paid plan graduates the user off the free tier. Drop any
        # free-config enrollment so the nightly free-quota reset / membership
        # recheck no longer treat this user as a free config and clobber their
        # paid traffic limit (or membership-suspend them).
        self.db.query(FreeConfigEnrollment).filter(
            FreeConfigEnrollment.user_id == user.id
        ).delete(synchronize_session=False)

        # A referred user who just bought a paid plan still counts toward their
        # referrer's traffic bonus (paid branch). Refresh the referrer's limit.
        #
        # The session is autoflush=False, and count_qualifying() below runs a
        # raw aggregate query that only sees committed/flushed DB state. This
        # buyer's expires_at/status were just set above and the enrollment row
        # was just deleted, but both are still pending in this session. Flush
        # first so the recompute sees the buyer as a qualifying paid referee
        # instead of miscounting them as neither free nor paid (mirrors the
        # flush in tasks/free_config_tasks.py::_recompute_referrer).
        if user.referred_by_user_id:
            self.db.flush()
            from app.services.referral.bonus_service import ReferralBonusService

            referrer = (
                self.db.query(AdminUser)
                .filter(AdminUser.id == user.referred_by_user_id)
                .first()
            )
            if referrer is not None:
                ReferralBonusService(self.db).apply_effective_limit(referrer)

    def _maybe_award_referral(self, user: AdminUser, order: UserOrder) -> None:
        """If user was referred and referral is enabled, credit the referrer."""
        if not user.referred_by_user_id:
            return

        config = (
            self.db.query(AdminReferralConfig)
            .filter(
                AdminReferralConfig.admin_id == user.admin_id,
                AdminReferralConfig.is_enabled == True,  # noqa: E712
            )
            .first()
        )
        if not config or config.reward_type not in ("cashback", "both"):
            return

        # Reward on the full package price, not just the cash charged, so that
        # orders paid fully or partly from wallet still credit the referrer.
        # price = cash remainder (amount_tomans) + wallet credit applied.
        price_basis = (order.amount_tomans or Decimal("0")) + (
            order.wallet_credit_applied_tomans or Decimal("0")
        )
        reward = (price_basis * config.reward_percentage / Decimal("100")).quantize(
            Decimal("0.01")
        )
        if reward <= 0:
            return

        referrer = (
            self.db.query(AdminUser)
            .filter(AdminUser.id == user.referred_by_user_id)
            .first()
        )
        if not referrer:
            return

        record_wallet_txn(self.db, referrer, reward, "referral", order.id)
        earning = AdminReferralEarning(
            admin_id=user.admin_id,
            referrer_user_id=referrer.id,
            referred_user_id=user.id,
            order_id=order.id,
            commission_percent=config.reward_percentage,
            amount_tomans=reward,
        )
        self.db.add(earning)
        self.db.commit()

        self.router.send_to_end_user(
            referrer.id,
            template_for(getattr(referrer, "language", "fa")).format_referral_reward(
                reward, referrer.wallet_credit_tomans
            ),
        )

    def _deliver_connections(self, user: AdminUser) -> None:
        """Generate v2 hero message with regenerated password + sub link + country grid.

        Sends via NotificationRouter with inline keyboard (3 guides + my_connections).
        Password is regenerated on every approval so plaintext is fresh in the hero
        and stored encrypted-at-rest (``password_enc``) for later display.
        """
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup

        # Regenerate password on every approval → dual-stored hash + enc
        new_pw = secrets.token_urlsafe(6)[:8]
        set_password(user, new_pw)

        # Backfill token for legacy users created before this invariant existed.
        # New users get a token at /start (end_user_start.py); admin-created
        # users get one at admin_api.py:295. This catches anyone who fell through.
        if not user.subscription_token:
            user.subscription_token = secrets.token_hex(16)

        self.db.commit()

        # Build URLs
        sub_url = (
            f"{get_subscription_base_url(self.db, user.admin_id)}"
            f"/api/v1/user/sub/{user.subscription_token}"
        )
        dash_url = get_dashboard_base_url(self.db, user.admin_id) + "/user/login"

        # Build country list from current region's breakdown
        macro_region = user.region.macro_region if user.region else "eu"
        svc = ConnectionStringService(self.db)
        breakdown = svc.generate_country_breakdown(user, macro_region)
        countries = [
            (code, country_flag(code), get_country_name(code))
            for code in breakdown.keys()
        ]

        region_info = MACRO_REGIONS.get(
            macro_region,
            {"flag": "\U0001f310", "name": "Unknown"},
        )
        limit_gb = (
            float(user.traffic_limit_bytes) / 1024**3
            if user.traffic_limit_bytes
            else None
        )
        package_name = ""
        if user.current_order and user.current_order.package_snapshot:
            package_name = user.current_order.package_snapshot.get("name", "")

        tpl = template_for(getattr(user, "language", "fa"))
        msg = tpl.format_user_activated_v2(
            package_name=package_name,
            limit_gb=limit_gb,
            expiry_date=(str(user.expires_at.date()) if user.expires_at else "-"),
            region_flag=region_info["flag"],
            region_name=region_info["name"],
            username=user.username,
            password=new_pw,
            dashboard_url=dash_url,
            subscription_url=sub_url,
            countries=countries,
        )

        # Inline keyboard: 3 guide buttons + My Connections
        lang = getattr(user, "language", "fa") or "fa"
        guide_labels = {
            "fa": {
                "android": "🤖 اندروید",
                "ios": "🍎 آیفون",
                "windows": "💻 ویندوز",
                "conn": "🔗 اتصالات من",
            },
            "en": {
                "android": "🤖 Android",
                "ios": "🍎 iOS",
                "windows": "💻 Windows",
                "conn": "🔗 My Connections",
            },
        }.get(
            lang,
            {
                "android": "🤖 Android",
                "ios": "🍎 iOS",
                "windows": "💻 Windows",
                "conn": "🔗 My Connections",
            },
        )
        kb = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        guide_labels["android"], callback_data="guide:android"
                    ),
                    InlineKeyboardButton(
                        guide_labels["ios"], callback_data="guide:ios"
                    ),
                    InlineKeyboardButton(
                        guide_labels["windows"], callback_data="guide:windows"
                    ),
                ],
                [
                    InlineKeyboardButton(
                        guide_labels["conn"], callback_data="connections"
                    )
                ],
            ]
        )

        self.router.send_to_end_user(user.id, msg, reply_markup=kb)
