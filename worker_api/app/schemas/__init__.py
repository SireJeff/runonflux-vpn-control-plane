"""
Pydantic schemas for FluxVPN Platform
Request/response validation schemas organized by category
"""

# Common schemas
from app.schemas.common import (
    DashboardStats,
    ErrorResponse,
    FilterParams,
    HealthCheckResponse,
    PaginatedResponse,
    PaginationParams,
    SortParams,
    SuccessResponse,
    SystemStats,
    TrialActivateRequest,
    TrialActivateResponse,
)

# Credential schemas
from app.schemas.credential import (
    CredentialDisplay,
    UserCredentialCreate,
    UserCredentialResponse,
    UserCredentialUpdate,
    UserCredentialWithProtocol,
    UserProtocolAssignmentCreate,
    UserProtocolAssignmentResponse,
    UserProtocolAssignmentWithDetails,
)

# IP Management schemas
from app.schemas.ip_management import (
    AvailableLocation,
    IPChangeQuotaCreate,
    IPChangeQuotaResponse,
    IPChangeRequest,
    IPChangeRequestCreate,
    IPChangeRequestResponse,
    IPChangeRequestUpdate,
    IPChangeResponse,
    ProtocolInstanceCreate,
    ProtocolInstanceResponse,
    ProtocolInstanceUpdate,
    QuotaStatus,
)

# Payment schemas
from app.schemas.payment import (
    PaymentCreate,
    PaymentInitiate,
    PaymentInitiateResponse,
    PaymentResponse,
    PaymentUpdate,
    WalletHistory,
    WalletTransactionCreate,
    WalletTransactionResponse,
    WithdrawalRequestCreate,
    WithdrawalRequestResponse,
    WithdrawalRequestSubmit,
    WithdrawalRequestSubmitResponse,
    WithdrawalRequestUpdate,
)

# Subscription schemas
from app.schemas.subscription import (  # Protocol; Plan; Subscription
    ProtocolCreate,
    ProtocolResponse,
    ProtocolUpdate,
    SubscriptionCreate,
    SubscriptionPlanCreate,
    SubscriptionPlanResponse,
    SubscriptionPlanUpdate,
    SubscriptionPurchaseRequest,
    SubscriptionPurchaseResponse,
    SubscriptionResponse,
    SubscriptionUpdate,
    SubscriptionWithDetails,
    SubscriptionWithPlan,
)

# Super Admin schemas
from app.schemas.super_admin import (
    AdminDetailResponse,
    AdminListResponse,
    ApproveAdminRequest,
    CreditWalletRequest,
    PlatformAnalytics,
    PlatformSettingsResponse,
    ReviewOrderRequest,
    UpdateSettingsRequest,
    WireOrderResponse,
)

# Support schemas
from app.schemas.support import (
    MessageSendRequest,
    MessageSendResponse,
    SupportMessageCreate,
    SupportMessageResponse,
    SupportTicketCreate,
    SupportTicketResponse,
    SupportTicketUpdate,
    SupportTicketWithMessages,
    TicketCreateRequest,
    TicketCreateResponse,
)

# User schemas
from app.schemas.user import (
    ReferralStats,
    TokenPairResponse,
    UserCreate,
    UserProfile,
    UserResponse,
    UserUpdate,
    UserWithWallet,
    WalletBalance,
)

__all__ = [
    # Common
    "SuccessResponse",
    "ErrorResponse",
    "PaginatedResponse",
    "HealthCheckResponse",
    "PaginationParams",
    "SortParams",
    "FilterParams",
    "DashboardStats",
    "SystemStats",
    "TrialActivateRequest",
    "TrialActivateResponse",
    # User
    "UserCreate",
    "UserUpdate",
    "UserResponse",
    "UserProfile",
    "UserWithWallet",
    "ReferralStats",
    "WalletBalance",
    "TokenPairResponse",
    # Subscription
    "ProtocolCreate",
    "ProtocolUpdate",
    "ProtocolResponse",
    "SubscriptionPlanCreate",
    "SubscriptionPlanUpdate",
    "SubscriptionPlanResponse",
    "SubscriptionCreate",
    "SubscriptionUpdate",
    "SubscriptionResponse",
    "SubscriptionWithPlan",
    "SubscriptionWithDetails",
    "SubscriptionPurchaseRequest",
    "SubscriptionPurchaseResponse",
    # Payment
    "PaymentCreate",
    "PaymentUpdate",
    "PaymentResponse",
    "PaymentInitiate",
    "PaymentInitiateResponse",
    "WalletTransactionCreate",
    "WalletTransactionResponse",
    "WalletHistory",
    "WithdrawalRequestCreate",
    "WithdrawalRequestUpdate",
    "WithdrawalRequestResponse",
    "WithdrawalRequestSubmit",
    "WithdrawalRequestSubmitResponse",
    # Credential
    "UserCredentialCreate",
    "UserCredentialUpdate",
    "UserCredentialResponse",
    "UserCredentialWithProtocol",
    "CredentialDisplay",
    "UserProtocolAssignmentCreate",
    "UserProtocolAssignmentResponse",
    "UserProtocolAssignmentWithDetails",
    # IP Management
    "ProtocolInstanceCreate",
    "ProtocolInstanceUpdate",
    "ProtocolInstanceResponse",
    "AvailableLocation",
    "IPChangeRequestCreate",
    "IPChangeRequestUpdate",
    "IPChangeRequestResponse",
    "IPChangeRequest",
    "IPChangeResponse",
    "IPChangeQuotaCreate",
    "IPChangeQuotaResponse",
    "QuotaStatus",
    # Support
    "SupportTicketCreate",
    "SupportTicketUpdate",
    "SupportTicketResponse",
    "SupportTicketWithMessages",
    "SupportMessageCreate",
    "SupportMessageResponse",
    "TicketCreateRequest",
    "TicketCreateResponse",
    "MessageSendRequest",
    "MessageSendResponse",
    # Super Admin
    "AdminListResponse",
    "AdminDetailResponse",
    "ApproveAdminRequest",
    "CreditWalletRequest",
    "WireOrderResponse",
    "ReviewOrderRequest",
    "PlatformSettingsResponse",
    "UpdateSettingsRequest",
    "PlatformAnalytics",
]
