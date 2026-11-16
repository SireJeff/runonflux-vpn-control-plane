"""
Flux DNS Manager (FDM) Celery Tasks

Background tasks for:
- Syncing all active deployments with Cloudflare DNS
- Syncing individual deployments
- Cleaning up old sync logs
- Daily rebalance of domain user counts
- Checking FDM IPs for Iranian filtering (check-host.net)
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from celery import shared_task

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.fdm import FdmDeployment, FdmSyncLog
from app.services.fdm import FdmSyncService
from app.services.fdm.iran_reach import IranReachChecker

logger = logging.getLogger(__name__)


# ============================================================================
# FDM SYNC TASKS
# ============================================================================


@shared_task(
    name="fdm.sync_all_deployments",
    acks_late=True,  # Redeliver on worker crash
    task_reject_on_worker_lost=True,  # Requeue if worker dies mid-task
    autoretry_for=(Exception,),  # Retry transient failures
    max_retries=3,
    retry_backoff=60,  # 60s, 120s, 240s
    retry_backoff_max=600,
    retry_jitter=False,  # Deterministic for debugging
    default_retry_delay=60,
)
def sync_all_deployments():
    """Sync all active FDM deployments with Cloudflare DNS.

    Resilience:
    - acks_late + reject_on_worker_lost: task re-delivered on worker crash
    - autoretry_for: transient exceptions retried 3x with exponential backoff
    - Each pre-sync phase is individually try/excepted (see FdmSyncService._run_phase)
    - One deployment failing does not abort the cycle

    Runs on a 10-minute schedule via celery-beat (see celery_config.py).

    Returns:
        Dict with success/partial/failed counts and timestamp.
    """
    logger.info("Starting FDM sync for all deployments")
    db = SessionLocal()

    try:
        sync_service = FdmSyncService(db)
        # asyncio.run() creates a fresh event loop each call — avoids the
        # deprecation warnings + state leaks of get_event_loop().
        results = asyncio.run(sync_service.sync_all_deployments())

        success_count = sum(1 for r in results.values() if r.status == "success")
        partial_count = sum(1 for r in results.values() if r.status == "partial")
        failed_count = sum(1 for r in results.values() if r.status == "failed")

        logger.info(
            f"FDM sync all deployments completed: "
            f"{success_count} success, {partial_count} partial, {failed_count} failed"
        )

        return {
            "success": success_count,
            "partial": partial_count,
            "failed": failed_count,
            "total": len(results),
            "timestamp": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
        }

    except Exception as exc:
        # Re-raise so autoretry_for kicks in. The decorator handles retry.
        logger.error("FDM sync all deployments failed (will retry): %s", exc)
        raise
    finally:
        db.close()


@shared_task(name="fdm.sync_deployment")
def sync_deployment(deployment_id: int):
    """
    Sync a single FDM deployment with Cloudflare DNS.

    This task can be triggered manually to sync a specific deployment.
    It orchestrates the complete DNS synchronization workflow for the
    specified deployment.

    Args:
        deployment_id: ID of the FdmDeployment to sync

    Returns:
        Dictionary with sync results including:
        - deployment_id: ID of the deployment synced
        - status: Sync status (success, partial, failed)
        - domains_updated: Number of DNS records updated
        - timestamp: UTC timestamp of sync completion

    Raises:
        Exception: If deployment not found or sync fails critically
    """
    logger.info("Starting FDM sync for deployment_id=%s", deployment_id)
    db = SessionLocal()

    try:
        # Query deployment
        deployment = (
            db.query(FdmDeployment).filter(FdmDeployment.id == deployment_id).first()
        )

        if not deployment:
            logger.error("Deployment not found: deployment_id=%s", deployment_id)
            return {
                "deployment_id": deployment_id,
                "status": "not_found",
                "error": "Deployment not found",
                "timestamp": datetime.now(timezone.utc)
                .replace(tzinfo=None)
                .isoformat(),
            }

        # Initialize sync_log to prevent UnboundLocalError in exception handler
        sync_log = None

        # Run async sync in sync context
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        try:
            # Create sync service and run sync
            sync_service = FdmSyncService(db)
            sync_log = loop.run_until_complete(sync_service.sync_deployment(deployment))

            logger.info(
                f"FDM sync completed for {deployment.flux_app_name}: "
                f"status={sync_log.status}, domains_updated={sync_log.domains_updated}"
            )

            return {
                "deployment_id": deployment_id,
                "flux_app_name": deployment.flux_app_name,
                "status": sync_log.status,
                "domains_updated": sync_log.domains_updated,
                "timestamp": datetime.now(timezone.utc)
                .replace(tzinfo=None)
                .isoformat(),
            }

        finally:
            loop.close()

    except Exception as exc:
        logger.error("FDM sync failed for deployment_id=%s: %s", deployment_id, exc)
        result = {
            "deployment_id": deployment_id,
            "status": "error",
            "error": str(exc),
            "timestamp": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
        }
        # Only include sync_log info if it was successfully created
        if sync_log is not None:
            result["sync_log_status"] = sync_log.status
            result["domains_updated"] = sync_log.domains_updated
        return result
    finally:
        db.close()


@shared_task(name="fdm.reconcile_app")
def reconcile_app(app_name: str):
    """On-demand scoped reconcile for one app (toggle/delete trigger).

    Thin async wrapper around FdmSyncService.reconcile_app. See that method
    for semantics (operator-driven, no 30-min grace).
    """
    logger.info("FDM scoped reconcile for app=%s", app_name)
    db = SessionLocal()
    try:
        sync_service = FdmSyncService(db)
        return asyncio.run(sync_service.reconcile_app(app_name))
    except Exception as exc:
        logger.error("FDM reconcile_app failed for %s: %s", app_name, exc)
        raise
    finally:
        db.close()


@shared_task(
    name="fdm.check_iran_reachability",
    soft_time_limit=300,
    time_limit=360,
)
def check_iran_reachability():
    """Check FDM IPs from check-host.net's Iranian nodes (see iran_reach.py).

    Collects the results submitted on the previous run, then submits a small
    batch of new checks. No retries: the next beat run is the retry, and any
    failure only leaves the stored verdicts as they were (fail-open).
    """
    if not settings.FDM_IRAN_REACH_ENABLED:
        return {"skipped": "disabled"}
    db = SessionLocal()
    try:
        summary = asyncio.run(IranReachChecker(db).run())
        logger.info("FDM Iran reachability run: %s", summary)
        return summary
    except Exception as exc:
        db.rollback()
        logger.warning("FDM Iran reachability run failed: %s", exc, exc_info=True)
        return {"error": str(exc)}
    finally:
        db.close()


# ============================================================================
# FDM MAINTENANCE TASKS
# ============================================================================


@shared_task(name="fdm.cleanup_old_sync_logs")
def cleanup_old_sync_logs(days: int = 7):
    """
    Cleanup old FDM sync logs beyond retention period.

    This task runs daily and removes sync log entries older than
    the specified retention period to manage database size.

    Args:
        days: Number of days to retain logs (default: 7)

    Returns:
        Dictionary with cleanup results including:
        - deleted: Number of log entries deleted
        - cutoff_date: ISO timestamp of cutoff date
        - timestamp: UTC timestamp of cleanup completion
    """
    logger.info("Starting cleanup of old FDM sync logs (days=%s)", days)
    db = SessionLocal()

    try:
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)

        # Delete old sync logs
        deleted = (
            db.query(FdmSyncLog)
            .filter(FdmSyncLog.created_at < cutoff)
            .delete(synchronize_session=False)
        )

        db.commit()

        logger.info(
            f"FDM sync log cleanup completed: deleted={deleted} logs older than {cutoff}"
        )

        return {
            "deleted": deleted,
            "cutoff_date": cutoff.isoformat(),
            "timestamp": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
        }

    except Exception as exc:
        logger.error("FDM sync log cleanup failed: %s", exc)
        db.rollback()
        return {
            "error": str(exc),
            "timestamp": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
        }
    finally:
        db.close()


# ============================================================================
# FDM REBALANCE TASKS
# ============================================================================


@shared_task(name="fdm.rebalance_domain_counts")
def rebalance_domain_counts():
    """
    Daily task: recount actual active users per domain and fix counter drift.

    For each healthy domain, counts active users with assigned_domain_id
    pointing to it and updates assigned_users_count to match.

    Returns:
        Dictionary with rebalance results including:
        - fixed: Number of domains whose counts were corrected
        - total: Total number of healthy domains checked
        - timestamp: UTC timestamp of rebalance completion
    """
    logger.info("Starting daily FDM domain count rebalance")
    db = SessionLocal()

    try:
        from app.models.admin_users import AdminUser
        from app.models.fdm import FdmDomain

        domains = db.query(FdmDomain).filter(FdmDomain.health_status == "healthy").all()

        fixed = 0
        for domain in domains:
            actual_count = (
                db.query(AdminUser)
                .filter(
                    AdminUser.assigned_domain_id == domain.id,
                    AdminUser.status == "active",
                )
                .count()
            )

            if domain.assigned_users_count != actual_count:
                logger.info(
                    f"Rebalancing {domain.domain_name}: "
                    f"counted={domain.assigned_users_count} -> actual={actual_count}"
                )
                domain.assigned_users_count = actual_count
                fixed += 1

        db.commit()

        logger.info(
            f"Rebalance complete: {fixed} domains corrected out of {len(domains)}"
        )

        return {
            "fixed": fixed,
            "total": len(domains),
            "timestamp": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
        }

    except Exception as exc:
        logger.error("FDM domain count rebalance failed: %s", exc)
        db.rollback()
        return {
            "error": str(exc),
            "timestamp": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
        }
    finally:
        db.close()
