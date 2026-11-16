"""
Flux Node Discovery Celery Tasks

Periodic tasks for maintaining the Flux node list cache.
These tasks run in the background to ensure the node list stays fresh.

Tasks:
- refresh_flux_node_list: Daily refresh of the node list from Flux API
- health_check_flux_nodes: Optional health check of all cached nodes

Schedule: Daily at 2 AM via Celery Beat (see celery_config.py)
"""

import logging
from datetime import datetime
from typing import Any, Dict

from celery import shared_task
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.services.flux.node_discovery import (
    NodeDiscoveryService,
    get_node_discovery_service,
)

logger = logging.getLogger(__name__)


@shared_task(
    name="flux.refresh_flux_node_list",
    bind=True,
    max_retries=3,
    default_retry_delay=300,  # 5 minutes
)
def refresh_flux_node_list(self) -> Dict[str, Any]:
    """
    Refresh the Flux node list from the centralized API.

    This task:
    1. Fetches the node list from /flux_node_list endpoint
    2. Health checks each node
    3. Updates the cache with healthy nodes
    4. Logs statistics

    Scheduled: Daily at 2 AM UTC via Celery Beat

    Returns:
        Dictionary with refresh statistics
    """
    logger.info("Starting Flux node list refresh...")

    try:
        # Get the singleton node discovery service
        discovery = get_node_discovery_service()

        # Refresh the cache
        stats = (
            discovery._refresh_cache() if hasattr(discovery, "_refresh_cache") else None
        )

        if stats is None:
            # Use the public API instead
            import asyncio

            stats = asyncio.run(discovery.refresh_cache())

        # Log the results
        logger.info(
            f"Flux node list refresh complete: "
            f"{stats.get('healthy_nodes', 0)}/{stats.get('total_nodes', 0)} healthy"
        )

        return stats

    except Exception as e:
        logger.error(f"Flux node list refresh failed: {e}")

        # Retry with backoff
        if self.request.retries < self.max_retries:
            logger.info(
                f"Retrying node list refresh (attempt {self.request.retries + 1})..."
            )
            raise self.retry(exc=e)

        return {
            "status": "error",
            "error": str(e),
            "timestamp": datetime.now().isoformat(),
        }


@shared_task(
    name="flux.health_check_flux_nodes",
    bind=True,
)
def health_check_flux_nodes(self) -> Dict[str, Any]:
    """
    Health check all cached Flux nodes.

    This task runs more frequently than the full refresh to catch
    nodes that have gone down since the last refresh.

    Returns:
        Dictionary with health check statistics
    """
    logger.info("Starting Flux node health check...")

    try:
        discovery = get_node_discovery_service()

        # Get current cache stats
        stats_before = discovery.get_cache_stats()

        # Perform health checks
        import asyncio

        nodes = discovery._cache.get_all_nodes()
        asyncio.run(discovery._health_check_nodes(nodes))

        # Get updated stats
        stats_after = discovery.get_cache_stats()

        logger.info(
            f"Flux node health check complete: "
            f"{stats_after.get('healthy_nodes', 0)}/{stats_after.get('total_nodes', 0)} healthy"
        )

        return {
            "before": stats_before,
            "after": stats_after,
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"Flux node health check failed: {e}")
        return {
            "status": "error",
            "error": str(e),
            "timestamp": datetime.now().isoformat(),
        }


@shared_task(
    name="flux.report_flux_node_stats",
)
def report_flux_node_stats() -> Dict[str, Any]:
    """
    Report current Flux node statistics for monitoring.

    This task can be called by monitoring systems to get the
    current state of the node cache.

    Returns:
        Dictionary with current node statistics
    """
    try:
        discovery = get_node_discovery_service()
        stats = discovery.get_cache_stats()

        logger.info(f"Flux node stats: {stats}")

        return stats

    except Exception as e:
        logger.error(f"Failed to get Flux node stats: {e}")
        return {
            "status": "error",
            "error": str(e),
            "timestamp": datetime.now().isoformat(),
        }


@shared_task(
    name="flux.purge_stale_nodes",
)
def purge_stale_nodes(max_age_hours: int = 48) -> Dict[str, Any]:
    """
    Remove nodes that have been unhealthy for too long.

    Args:
        max_age_hours: Maximum hours to keep unhealthy nodes

    Returns:
        Dictionary with purge statistics
    """
    logger.info(f"Purging nodes unhealthy for >{max_age_hours} hours...")

    try:
        discovery = get_node_discovery_service()
        cache = discovery._cache

        from datetime import timedelta

        cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
        purged_count = 0

        # Nodes to remove
        to_remove = []

        for node in cache.get_all_nodes():
            if (
                not node.is_healthy
                and node.last_checked
                and node.last_checked < cutoff_time
            ):
                to_remove.append(node)

        # Remove stale nodes
        for node in to_remove:
            cache.remove_node(node.ip, node.port)
            purged_count += 1
            logger.info(f"Purged stale node: {node.ip} (failures: {node.failures})")

        return {
            "purged_count": purged_count,
            "max_age_hours": max_age_hours,
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"Failed to purge stale nodes: {e}")
        return {
            "status": "error",
            "error": str(e),
            "timestamp": datetime.now().isoformat(),
        }
