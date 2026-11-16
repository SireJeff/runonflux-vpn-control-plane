"""
API v1 Endpoints
"""

from app.api.v1.endpoints import (
    admin,
    admin_api,
    admin_dashboard,
    auth,
    auth_v2,
    credentials,
    end_user,
    fdm,
    internal_v2,
    ip_management,
    mvp,
    nodes,
    payments,
    subscriptions,
    super_admin,
    support,
    users,
    webhooks,
)

__all__ = [
    "auth",
    "auth_v2",
    "users",
    "subscriptions",
    "payments",
    "ip_management",
    "support",
    "credentials",
    "admin",
    "admin_api",
    "webhooks",
    "nodes",
    "admin_dashboard",
    "mvp",
    "fdm",
    "super_admin",
    "end_user",
    "internal_v2",
]
