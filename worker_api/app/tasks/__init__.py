"""
Celery Tasks Module

Background tasks for FluxVPN platform automation:
- Subscription management (auto-renewal, expiration, warnings)
- Usage tracking (bandwidth monitoring, alerts)
- FluxCloud infrastructure monitoring
- Payment processing
"""

# Import all task modules to register them with Celery
from app.tasks import (
    billing_tasks,
    broadcast_tasks,
    compliance_tasks,
    end_user_notifications,
    fdm_tasks,
    flux_tasks,
    free_config_tasks,
    ip_tasks,
    node_tasks,
    subscription_tasks,
    tld_analytics,
    usage_tasks,
)

__all__ = [
    "billing_tasks",
    "broadcast_tasks",
    "end_user_notifications",
    "subscription_tasks",
    "usage_tasks",
    "compliance_tasks",
    "ip_tasks",
    "fdm_tasks",
    "flux_tasks",
    "free_config_tasks",
    "node_tasks",
    "tld_analytics",
]
