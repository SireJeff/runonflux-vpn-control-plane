"""
Celery configuration and periodic task scheduling
"""

from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

# Create Celery app
celery_app = Celery(
    "fluxvpn_worker", broker=settings.REDIS_URL, backend=settings.REDIS_URL
)

# Celery configuration
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,  # 1 hour max per task
    task_soft_time_limit=3000,  # 50 minutes soft limit
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=1000,
    broker_connection_retry_on_startup=True,
)

# Periodic task schedule
celery_app.conf.beat_schedule = {
    # ============================================================================
    # FLUX NODE DISCOVERY (Hybrid Client - Node-First Queries)
    # ============================================================================
    # Refresh Flux node list - daily at 2 AM UTC
    "flux.refresh_flux_node_list": {
        "task": "flux.refresh_flux_node_list",
        "schedule": crontab(hour=2, minute=0),  # Daily at 2 AM
        "options": {"queue": "monitoring"},
    },
    # Health check Flux nodes - every 6 hours
    "flux.health_check_flux_nodes": {
        "task": "flux.health_check_flux_nodes",
        "schedule": crontab(hour="*/6"),  # Every 6 hours
        "options": {"queue": "monitoring"},
    },
    # Report Flux node stats - hourly
    "flux.report_flux_node_stats": {
        "task": "flux.report_flux_node_stats",
        "schedule": 3600.0,  # 1 hour
        "options": {"queue": "monitoring"},
    },
    # Purge stale nodes - weekly (Sunday at 3 AM UTC)
    "flux.purge_stale_nodes": {
        "task": "flux.purge_stale_nodes",
        "schedule": crontab(hour=3, minute=0, day_of_week=0),
        "options": {"queue": "maintenance"},
    },
    # ============================================================================
    # INFRASTRUCTURE MONITORING (FluxCloud)
    # ============================================================================
    # Endpoint-health decisions belong to FDM's app/port-aware liveness gate.
    # Legacy health-check/restart task names remain registered as no-ops for
    # queued deliveries, but must not be scheduled again.
    # Health report - every hour
    "generate-health-report": {
        "task": "flux.generate_health_report",
        "schedule": 3600.0,  # 1 hour
        "options": {"queue": "monitoring"},
    },
    # Cost calculation - daily at 00:00 UTC
    "calculate-deployment-costs": {
        "task": "flux.get_deployment_costs",
        "schedule": crontab(hour=0, minute=0),
        "options": {"queue": "reports"},
    },
    # ============================================================================
    # SUBSCRIPTION MANAGEMENT (Week 8)
    # ============================================================================
    # Auto-renewal processing - daily at 00:00 UTC
    "process-auto-renewals": {
        "task": "subscriptions.process_auto_renewals",
        "schedule": crontab(hour=0, minute=0),
        "options": {"queue": "subscriptions"},
    },
    # Renewal warnings - daily at 09:00 UTC
    "send-renewal-warnings": {
        "task": "subscriptions.send_renewal_warnings",
        "schedule": crontab(hour=9, minute=0),
        "options": {"queue": "notifications"},
    },
    # Expire subscriptions - every hour
    "expire-subscriptions": {
        "task": "subscriptions.expire_subscriptions",
        "schedule": 3600.0,  # 1 hour
        "options": {"queue": "subscriptions"},
    },
    # Expire trials - every hour
    "expire-trials": {
        "task": "subscriptions.expire_trials",
        "schedule": 3600.0,  # 1 hour
        "options": {"queue": "subscriptions"},
    },
    # Calculate churn rate - daily at 01:00 UTC
    "calculate-churn-rate": {
        "task": "subscriptions.calculate_churn_rate",
        "schedule": crontab(hour=1, minute=0),
        "options": {"queue": "analytics"},
    },
    # Cleanup old subscriptions - weekly (Sunday at 02:00 UTC)
    "cleanup-old-subscriptions": {
        "task": "subscriptions.cleanup_old_subscriptions",
        "schedule": crontab(hour=2, minute=0, day_of_week=0),
        "options": {"queue": "maintenance"},
    },
    # ============================================================================
    # USAGE TRACKING (Week 8)
    # ============================================================================
    # Sync protocol usage - every 15 minutes
    "sync-protocol-usage": {
        "task": "usage.sync_protocol_usage",
        "schedule": 900.0,  # 15 minutes
        "options": {"queue": "monitoring"},
    },
    # Check usage thresholds - hourly
    "check-usage-thresholds": {
        "task": "usage.check_usage_thresholds",
        "schedule": 3600.0,  # 1 hour
        "options": {"queue": "monitoring"},
    },
    # Aggregate daily usage - daily at 02:00 UTC
    "aggregate-daily-usage": {
        "task": "usage.aggregate_daily_usage",
        "schedule": crontab(hour=2, minute=0),
        "options": {"queue": "analytics"},
    },
    # Monitor concurrent connections - every 5 minutes
    "monitor-concurrent-connections": {
        "task": "usage.monitor_concurrent_connections",
        "schedule": 300.0,  # 5 minutes
        "options": {"queue": "monitoring"},
    },
    # Cleanup old logs - daily at 03:00 UTC (7-day retention)
    "cleanup-old-logs": {
        "task": "usage.cleanup_old_logs",
        "schedule": crontab(hour=3, minute=0),
        "options": {"queue": "maintenance"},
    },
    # Calculate bandwidth stats - hourly
    "calculate-bandwidth-stats": {
        "task": "usage.calculate_bandwidth_stats",
        "schedule": 3600.0,  # 1 hour
        "options": {"queue": "analytics"},
    },
    # ============================================================================
    # MAINTENANCE
    # ============================================================================
    # Cleanup old alerts - daily at 04:00 UTC
    "cleanup-old-alerts": {
        "task": "flux.cleanup_old_alerts",
        "schedule": crontab(hour=4, minute=0),
        "options": {"queue": "maintenance"},
    },
    # Cleanup soft-deleted users after retention expiry - daily at 04:30 UTC
    "compliance.cleanup-soft-deleted-users": {
        "task": "compliance.cleanup_soft_deleted_users",
        "schedule": crontab(hour=4, minute=30),
        "options": {"queue": "maintenance"},
    },
    # ============================================================================
    # END-USER NOTIFICATIONS (Reseller End-User Bot)
    # ============================================================================
    # Notify users whose subscription expires in ~3 days - daily at 9 AM UTC
    "notifications.subscription_expiring": {
        "task": "notifications.subscription_expiring",
        "schedule": crontab(hour=9, minute=0),
        "options": {"queue": "notifications"},
    },
    # Notify + mark users whose subscription expired yesterday - daily at 10 AM UTC
    "notifications.subscription_expired": {
        "task": "notifications.subscription_expired",
        "schedule": crontab(hour=10, minute=0),
        "options": {"queue": "notifications"},
    },
    # Mark pending orders older than 72h as expired - daily at 11 AM UTC
    "notifications.cleanup_pending_orders": {
        "task": "notifications.cleanup_pending_orders",
        "schedule": crontab(hour=11, minute=0),
        "options": {"queue": "notifications"},
    },
    # ============================================================================
    # BILLING (Reseller Platform)
    # ============================================================================
    # Wallet balance monitoring - every 15 minutes
    "check-wallet-balances": {
        "task": "billing.check_wallet_balances",
        "schedule": crontab(minute="*/15"),
        "options": {"queue": "billing"},
    },
    # ============================================================================
    # IP MANAGEMENT
    # ============================================================================
    # Cleanup old IP requests - daily at 03:00 UTC
    "ip.cleanup_old_ip_requests": {
        "task": "ip.cleanup_old_ip_requests",
        "schedule": crontab(hour=3, minute=0),
        "options": {"queue": "maintenance"},
    },
    # ============================================================================
    # FDM (Flux DNS Manager)
    # ============================================================================
    # Sync all deployments - every 10 minutes
    "fdm.sync_all_deployments": {
        "task": "fdm.sync_all_deployments",
        "schedule": getattr(settings, "FDM_SYNC_INTERVAL_SECONDS", 600.0),
        "options": {"queue": "fdm"},
    },
    # Iran reachability via check-host.net - every 10 minutes. Short run (a few
    # HTTP calls, never waits on results); the sync only reads its verdicts.
    "fdm.check_iran_reachability": {
        "task": "fdm.check_iran_reachability",
        "schedule": getattr(settings, "FDM_IRAN_REACH_RUN_INTERVAL", 600.0),
        "options": {"queue": "fdm"},
    },
    # Cleanup old sync logs - daily at 05:00 UTC
    "fdm.cleanup_old_sync_logs": {
        "task": "fdm.cleanup_old_sync_logs",
        "schedule": crontab(hour=5, minute=0),
        "options": {"queue": "maintenance"},
    },
    # Rebalance domain user counts - daily at 03:00 UTC
    "fdm.rebalance_domain_counts": {
        "task": "fdm.rebalance_domain_counts",
        "schedule": crontab(hour=3, minute=0),
        "options": {"queue": "maintenance"},
    },
    # ============================================================================
    # TLD ANALYTICS
    # ============================================================================
    # Daily TLD usage snapshot - daily at 03:17 UTC (analytics time-series)
    # 03:17, not 03:00: cleanup-old-logs + fdm.rebalance_domain_counts run at 03:00.
    "analytics.tld_snapshot": {
        "task": "analytics.tld_snapshot",
        "schedule": crontab(hour=3, minute=17),
        "options": {"queue": "analytics"},
    },
    # ============================================================================
    # FREE CONFIG (Per-User Daily Quota)
    # ============================================================================
    # Reset daily quotas (zero odometer + re-apply resolved limit) - daily at 00:00 UTC
    "free-config-reset-daily-quotas": {
        "task": "free_config.reset_daily_quotas",
        "schedule": crontab(hour=0, minute=0),  # 00:00 UTC
        "options": {"queue": "monitoring"},
    },
    # Re-check channel memberships (revoke/restore free access) - every 6h
    "free-config-recheck-memberships": {
        "task": "free_config.recheck_memberships",
        "schedule": crontab(minute=0, hour="*/6"),
        "options": {"queue": "monitoring"},
    },
}

# Task routing
celery_app.conf.task_routes = {
    "flux.*": {"queue": "flux"},
    "database.*": {"queue": "database"},
    "notifications.*": {"queue": "notifications"},
    "payments.*": {"queue": "payments"},
    "subscriptions.*": {"queue": "subscriptions"},
    "usage.*": {"queue": "monitoring"},
    "analytics.*": {"queue": "analytics"},
    "billing.*": {"queue": "billing"},
    "ip.*": {"queue": "ip"},
    "compliance.*": {"queue": "maintenance"},
    "fdm.*": {"queue": "fdm"},
}

# Autodiscover and register tasks from all task modules
# This must be after celery_app is fully configured
celery_app.autodiscover_tasks(["app"])
