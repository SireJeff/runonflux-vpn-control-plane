"""
SQLAlchemy models for FluxVPN Platform
All database tables organized by category
"""
from app.models.admin import AdminAlert, ReferralEarning, SupportMessage, SupportTicket
from app.models.admin_users import AdminUser
from app.models.admins import Admin
from app.models.broadcast import Broadcast  # noqa: F401
from app.models.credential import UserCredential, UserProtocolAssignment
from app.models.fdm import FdmDeployment, FdmDomain, FdmSyncLog
from app.models.fdm_ip_iran_reach import FdmIpIranReach
from app.models.fdm_ip_liveness import FdmIpLiveness
from app.models.flux_app_registration import FluxAppRegistration
from app.models.ip_management import IPChangeQuota, IPChangeRequest, ProtocolInstance
from app.models.logging import AuthLog, ConnectionLog
from app.models.observability import ApiRequestMetricHourly
from app.models.payment import Payment, WalletTransaction, WithdrawalRequest
from app.models.settings import SystemSettings
from app.models.subscription import Protocol, Subscription, SubscriptionPlan
from app.models.usage_analytics import BandwidthTimeSeries, ProtocolDailySummary
from app.models.usage_metrics import UsageMetricDaily, UsageMetricHourly
from app.models.user import User

# Backward compatibility aliases
Credential = UserCredential
from app.models.admin_bots import AdminBot
from app.models.admin_free_config import AdminFreeConfig
from app.models.free_config_channel import FreeConfigChannel
from app.models.free_config_global import FreeConfigGlobal
from app.models.free_config_enrollment import FreeConfigEnrollment
from app.models.admin_routing_config import AdminRoutingConfig
from app.models.admin_packages import AdminPackage
from app.models.admin_user_wallet_txn import AdminUserWalletTxn
from app.models.admin_referral import AdminReferralConfig, AdminReferralEarning
from app.models.admin_tld_state import AdminTldState
from app.models.platform_settings import PlatformSetting
from app.models.registered_tld import RegisteredTld
from app.models.tld_usage_daily import TldUsageDaily
from app.models.traffic_counters import TrafficCounter
from app.models.traffic_logs import TrafficLog
from app.models.user_adjustments import UserAdjustment
from app.models.user_credentials_v2 import UserCredentialV2
from app.models.user_orders import UserOrder
from app.models.user_regions import UserRegion
from app.models.ux import (
    ConnectionViolation,
    RenewalWarning,
    Translation,
    TrialActivation,
    UsageAlert,
)
from app.models.wallet_transaction_v2 import WalletTransactionV2
from app.models.wire_orders import WireOrder

# Backward compatibility alias for SupportMessage
TicketMessage = SupportMessage

# Export all models for easy importing
__all__ = [
    # Core (4 models)
    "User",
    "Protocol",
    "SubscriptionPlan",
    "Subscription",
    # Payment (3 models)
    "Payment",
    "WalletTransaction",
    "WithdrawalRequest",
    # Credentials (2 models + alias)
    "UserCredential",
    "UserProtocolAssignment",
    "Credential",  # Backward compatibility alias for UserCredential
    # IP Management (3 models)
    "ProtocolInstance",
    "IPChangeRequest",
    "IPChangeQuota",
    # UX Enhancements (5 models)
    "TrialActivation",
    "RenewalWarning",
    "ConnectionViolation",
    "UsageAlert",
    "Translation",
    # Admin & Monitoring (4 models + alias)
    "SupportTicket",
    "SupportMessage",
    "TicketMessage",  # Backward compatibility alias for SupportMessage
    "AdminAlert",
    "ReferralEarning",
    "SystemSettings",
    # Logging (2 models)
    "ConnectionLog",
    "AuthLog",
    # Usage metrics (2 models)
    "UsageMetricHourly",
    "UsageMetricDaily",
    # Observability
    "ApiRequestMetricHourly",
    # Usage analytics (2 models)
    "ProtocolDailySummary",
    "BandwidthTimeSeries",
    # FDM - Flux DNS Manager (3 models)
    "FdmDeployment",
    "FdmDomain",
    "FdmSyncLog",
    "FdmIpLiveness",
    "FdmIpIranReach",
    "FluxAppRegistration",
    # Reseller Platform (7 models)
    "Admin",
    "AdminUser",
    "UserCredentialV2",
    "UserRegion",
    "TrafficLog",
    "TrafficCounter",
    "WireOrder",
    "PlatformSetting",
    "RegisteredTld",
    "AdminTldState",
    "TldUsageDaily",
    "WalletTransactionV2",
    # Reseller End-User Bot (6 models)
    "AdminBot",
    "AdminPackage",
    "UserOrder",
    "UserAdjustment",
    "AdminReferralConfig",
    "AdminReferralEarning",
    "AdminUserWalletTxn",
    "AdminFreeConfig",
    "FreeConfigChannel",
    "FreeConfigGlobal",
    "FreeConfigEnrollment",
    "AdminRoutingConfig",
    "Broadcast",
]
