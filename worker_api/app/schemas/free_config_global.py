"""Pydantic schemas for the superadmin global free-config API (Task 9).

GlobalConfigResponse is the write-safe view of the FreeConfigGlobal
singleton: it exposes `has_token` (a boolean) and NEVER the encrypted
verification-bot token blob.
"""

from typing import Optional

from pydantic import BaseModel


class GlobalConfigResponse(BaseModel):
    is_enabled: bool
    default_daily_limit_mb: int
    default_max_free_users: Optional[int] = None
    has_token: bool
    verification_bot_username: Optional[str] = None


class GlobalConfigUpdate(BaseModel):
    is_enabled: Optional[bool] = None
    default_daily_limit_mb: Optional[int] = None
    default_max_free_users: Optional[int] = None


class GlobalTokenUpdate(BaseModel):
    token: str
