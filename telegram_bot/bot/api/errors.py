"""
FluxVPN API Error Classes
Custom exceptions for API error handling
"""
from typing import Any, Dict, Optional


class APIError(Exception):
    """Base API error"""

    def __init__(
        self,
        message: str = "An API error occurred",
        status_code: int = 500,
        details: Optional[Dict[str, Any]] = None,
    ):
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)

    def __str__(self) -> str:
        return f"[{self.status_code}] {self.message}"


class AuthenticationError(APIError):
    """401/403 errors - Token expired or invalid"""

    def __init__(
        self,
        message: str = "Authentication failed. Please restart the bot.",
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message=message, status_code=401, details=details)


class ValidationError(APIError):
    """422 errors - Invalid request data"""

    def __init__(
        self,
        message: str = "Invalid request data",
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message=message, status_code=422, details=details)


class InsufficientBalanceError(APIError):
    """402 errors - Not enough wallet balance"""

    def __init__(
        self,
        required: float = 0,
        available: float = 0,
        message: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        self.required = required
        self.available = available
        if message is None:
            message = f"Insufficient balance. Required: ${required:.2f}, Available: ${available:.2f}"
        super().__init__(message=message, status_code=402, details=details)


class NotFoundError(APIError):
    """404 errors - Resource not found"""

    def __init__(
        self,
        resource: str = "Resource",
        message: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        self.resource = resource
        if message is None:
            message = f"{resource} not found"
        super().__init__(message=message, status_code=404, details=details)


class ConflictError(APIError):
    """409 errors - Resource conflict (e.g., duplicate)"""

    def __init__(
        self,
        message: str = "Resource conflict",
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message=message, status_code=409, details=details)


class RateLimitError(APIError):
    """429 errors - Too many requests"""

    def __init__(
        self,
        retry_after: int = 60,
        message: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        self.retry_after = retry_after
        if message is None:
            message = f"Rate limit exceeded. Please try again in {retry_after} seconds."
        super().__init__(message=message, status_code=429, details=details)


class ServerError(APIError):
    """500+ errors - Server-side issues"""

    def __init__(
        self,
        message: str = "Server error. Please try again later.",
        status_code: int = 500,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message=message, status_code=status_code, details=details)


class NetworkError(APIError):
    """Connection/timeout errors"""

    def __init__(
        self,
        message: str = "Network error. Please check your connection.",
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message=message, status_code=0, details=details)


class TrialAlreadyUsedError(APIError):
    """User has already used their free trial"""

    def __init__(
        self,
        message: str = "You have already used your free trial.",
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message=message, status_code=409, details=details)


class SubscriptionExistsError(APIError):
    """User already has an active subscription for this protocol"""

    def __init__(
        self,
        protocol: str = "",
        message: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        self.protocol = protocol
        if message is None:
            message = f"You already have an active subscription for {protocol}."
        super().__init__(message=message, status_code=409, details=details)


class IPChangeLimitError(APIError):
    """User has reached IP change limit"""

    def __init__(
        self,
        used: int = 0,
        limit: int = 0,
        message: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        self.used = used
        self.limit = limit
        if message is None:
            message = f"IP change limit reached ({used}/{limit}). Limit resets next month."
        super().__init__(message=message, status_code=429, details=details)


def parse_api_error(status_code: int, response_data: Dict[str, Any]) -> APIError:
    """
    Parse API response and return appropriate error type.
    Call this when response.is_success is False.
    """
    detail = response_data.get("detail", "Unknown error")

    # Handle specific error messages
    detail_lower = detail.lower() if isinstance(detail, str) else ""

    if status_code == 401 or status_code == 403:
        return AuthenticationError(message=detail, details=response_data)

    if status_code == 402:
        # Try to parse required/available from response
        required = response_data.get("required", 0)
        available = response_data.get("available", 0)
        return InsufficientBalanceError(
            required=required, available=available, message=detail, details=response_data
        )

    if status_code == 404:
        return NotFoundError(message=detail, details=response_data)

    if status_code == 409:
        if "trial" in detail_lower:
            return TrialAlreadyUsedError(message=detail, details=response_data)
        if "subscription" in detail_lower or "already" in detail_lower:
            return SubscriptionExistsError(message=detail, details=response_data)
        return ConflictError(message=detail, details=response_data)

    if status_code == 422:
        return ValidationError(message=detail, details=response_data)

    if status_code == 429:
        retry_after = response_data.get("retry_after", 60)
        return RateLimitError(retry_after=retry_after, message=detail, details=response_data)

    if status_code >= 500:
        return ServerError(message=detail, status_code=status_code, details=response_data)

    return APIError(message=detail, status_code=status_code, details=response_data)
