"""
Common Pydantic schemas for shared responses
"""

from typing import Any, Generic, Optional, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


# ============================================================================
# STANDARD RESPONSES
# ============================================================================


class SuccessResponse(BaseModel):
    """Standard success response"""

    success: bool = True
    message: str
    data: Optional[Any] = None


class ErrorResponse(BaseModel):
    """Standard error response"""

    success: bool = False
    error: str
    details: Optional[str] = None
    error_code: Optional[str] = None


class PaginatedResponse(BaseModel, Generic[T]):
    """Paginated response wrapper"""

    items: list[T]
    total: int
    page: int
    page_size: int
    total_pages: int
    has_next: bool
    has_prev: bool


class HealthCheckResponse(BaseModel):
    """Health check response"""

    status: str = "healthy"
    service: str
    timestamp: str
    version: Optional[str] = None
    database: Optional[str] = None
    redis: Optional[str] = None


# ============================================================================
# REQUEST PARAMETERS
# ============================================================================


class PaginationParams(BaseModel):
    """Pagination parameters"""

    page: int = Field(default=1, ge=1, description="Page number")
    page_size: int = Field(default=20, ge=1, le=100, description="Items per page")


class SortParams(BaseModel):
    """Sorting parameters"""

    sort_by: Optional[str] = Field(None, description="Field to sort by")
    sort_order: str = Field(
        default="asc", pattern="^(asc|desc)$", description="Sort order"
    )


class FilterParams(BaseModel):
    """Common filter parameters"""

    search: Optional[str] = Field(None, description="Search query")
    status: Optional[str] = Field(None, description="Filter by status")
    date_from: Optional[str] = Field(None, description="Filter from date (ISO format)")
    date_to: Optional[str] = Field(None, description="Filter to date (ISO format)")


# ============================================================================
# STATISTICS & ANALYTICS
# ============================================================================


class DashboardStats(BaseModel):
    """User dashboard statistics"""

    active_subscriptions: int
    wallet_balance: str  # Formatted with currency
    total_referrals: int
    referral_earnings: str  # Formatted with currency
    data_used_today_gb: float
    ip_changes_remaining: int


class SystemStats(BaseModel):
    """System-wide statistics (admin only)"""

    total_users: int
    active_subscriptions: int
    total_revenue_usd: float
    pending_withdrawals: int
    open_support_tickets: int
    system_health: str  # healthy, degraded, down


# ============================================================================
# TRIAL & ONBOARDING
# ============================================================================


class TrialActivateRequest(BaseModel):
    """Request to activate free trial"""

    accept_terms: bool = Field(..., description="User must accept terms of service")


class TrialActivateResponse(BaseModel):
    """Response for trial activation"""

    success: bool
    trial_id: int
    expires_at: str
    credentials: list[Any]  # List of credential objects
    message: str
