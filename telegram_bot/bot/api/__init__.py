"""
FluxVPN API Client Package
"""
from .client import FluxVPNAPI, get_api
from .errors import (
    APIError,
    AuthenticationError,
    InsufficientBalanceError,
    NotFoundError,
    RateLimitError,
    ServerError,
    ValidationError,
)

__all__ = [
    "FluxVPNAPI",
    "get_api",
    "APIError",
    "AuthenticationError",
    "InsufficientBalanceError",
    "NotFoundError",
    "RateLimitError",
    "ServerError",
    "ValidationError",
]
