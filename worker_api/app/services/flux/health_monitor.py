"""
FluxCloud Health Monitor
Monitors health and performance of deployed VPN protocol instances
"""

import asyncio
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional, cast

from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import AdminAlert, ProtocolInstance
from app.services.flux.client import FluxCloudAPIException, FluxCloudClient
from app.services.flux.hybrid_client import FluxHybridClient

logger = logging.getLogger(__name__)


class HealthCheckResult:
    """Result of a health check"""

    def __init__(
        self,
        instance: ProtocolInstance,
        is_healthy: bool,
        response_time_ms: Optional[float] = None,
        error_message: Optional[str] = None,
        metrics: Optional[Dict] = None,
    ):
        self.instance = instance
        self.is_healthy = is_healthy
        self.response_time_ms = response_time_ms
        self.error_message = error_message
        self.metrics = metrics or {}
        self.checked_at = datetime.now()


class FluxHealthMonitor:
    """
    Monitors health and performance of FluxCloud-deployed instances

    Features:
    - Periodic health checks
    - Performance monitoring
    - Automatic alerting for failures
    - Instance recovery attempts
    """

    # Health check configuration
    HEALTH_CHECK_INTERVAL = 300  # 5 minutes
    UNHEALTHY_THRESHOLD = 3  # Failed checks before marking unhealthy
    RECOVERY_TIMEOUT = 60  # Seconds to wait for recovery

    def __init__(self, flux_client: Optional[FluxHybridClient] = None):
        """
        Initialize Health Monitor

        Args:
            flux_client: FluxHybridClient (creates new one if not provided)
                         Can also accept FluxCloudClient for backward compatibility
        """
        # Support both FluxHybridClient and legacy FluxCloudClient
        if flux_client is None:
            self.flux_client = FluxHybridClient()
        elif isinstance(flux_client, FluxCloudClient):
            # Wrap legacy client in hybrid client for consistency
            self.flux_client = FluxHybridClient(api_client=flux_client)
        else:
            self.flux_client = flux_client

        self._health_check_counts: Dict[int, int] = {}

    async def __aenter__(self):
        """Support `async with FluxHealthMonitor() as monitor:` — the form the
        flux celery tasks use. Returns self; cleanup happens in __aexit__."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Close the underlying flux client on context exit (also on error)."""
        await self.close()

    async def check_instance_health(
        self, instance: ProtocolInstance
    ) -> HealthCheckResult:
        """
        Check health of a single instance

        Args:
            instance: ProtocolInstance to check

        Returns:
            HealthCheckResult with status and metrics
        """
        logger.debug(f"Checking health for {instance.flux_app_name}")

        start_time = datetime.now()

        try:
            # Get health status from FluxCloud
            health_response = await self.flux_client.get_app_health(
                cast(str, instance.flux_app_name)
            )

            end_time = datetime.now()
            response_time = (end_time - start_time).total_seconds() * 1000  # ms

            # Parse health response
            is_healthy = health_response.get("status") == "healthy"
            metrics = {
                "uptime": health_response.get("uptime", 0),
                "cpu_usage": health_response.get("cpu_usage", 0),
                "ram_usage": health_response.get("ram_usage", 0),
                "network_rx": health_response.get("network_rx", 0),
                "network_tx": health_response.get("network_tx", 0),
            }

            return HealthCheckResult(
                instance=instance,
                is_healthy=is_healthy,
                response_time_ms=response_time,
                metrics=metrics,
            )

        except FluxCloudAPIException as e:
            logger.error(f"Health check failed for {instance.flux_app_name}: {str(e)}")

            return HealthCheckResult(
                instance=instance, is_healthy=False, error_message=str(e)
            )

        except Exception as e:
            logger.error(
                f"Unexpected error checking {instance.flux_app_name}: {str(e)}"
            )

            return HealthCheckResult(
                instance=instance,
                is_healthy=False,
                error_message=f"Unexpected error: {str(e)}",
            )

    async def check_all_instances(
        self, db: Session, protocol_id: Optional[int] = None
    ) -> List[HealthCheckResult]:
        """
        Check health of all instances (or all instances for a protocol)

        Args:
            db: Database session
            protocol_id: Optional protocol ID to filter by

        Returns:
            List of HealthCheckResult for all instances
        """
        logger.info("Starting health checks for all instances")

        # Query instances to check
        query = db.query(ProtocolInstance).filter_by(is_active=True)

        if protocol_id:
            query = query.filter_by(protocol_id=protocol_id)

        instances = query.all()

        logger.info(f"Checking health for {len(instances)} instances")

        # Run health checks concurrently
        tasks = [self.check_instance_health(instance) for instance in instances]
        results = await asyncio.gather(*tasks)

        # Update database with health check results
        await self._process_health_results(db, results)

        # Count healthy vs unhealthy
        healthy_count = sum(1 for r in results if r.is_healthy)
        unhealthy_count = len(results) - healthy_count

        logger.info(
            f"Health check complete: {healthy_count} healthy, {unhealthy_count} unhealthy"
        )

        return results

    async def _process_health_results(
        self, db: Session, results: List[HealthCheckResult]
    ):
        """
        Process health check results and update database

        Args:
            db: Database session
            results: List of health check results
        """
        for result in results:
            instance = result.instance
            instance_obj = cast(Any, instance)

            # Update last health check time
            instance_obj.last_health_check = result.checked_at
            db.commit()

            # Track failed health checks
            instance_key = int(instance.id)

            if not result.is_healthy:
                # Increment failed check count
                self._health_check_counts[instance_key] = (
                    self._health_check_counts.get(instance_key, 0) + 1
                )

                # Check if threshold exceeded
                if self._health_check_counts[instance_key] >= self.UNHEALTHY_THRESHOLD:
                    logger.warning(
                        f"Instance {instance.flux_app_name} exceeded unhealthy threshold"
                    )

                    # Mark instance as inactive
                    instance_obj.is_active = False
                    instance_obj.health_status = "unhealthy"
                    db.commit()

                    # Create admin alert
                    await self._create_unhealthy_alert(db, result)

                    # Attempt recovery
                    await self._attempt_recovery(db, instance)

            else:
                # Reset failed check count on successful health check
                self._health_check_counts[instance_key] = 0
                instance_obj.health_status = "healthy"

                # Re-activate if it was previously marked inactive
                if not instance.is_active:
                    logger.info(
                        f"Instance {instance.flux_app_name} recovered, marking as active"
                    )
                    instance_obj.is_active = True

                    # Create recovery alert
                    await self._create_recovery_alert(db, instance)

                db.commit()

    async def _create_unhealthy_alert(self, db: Session, result: HealthCheckResult):
        """
        Create admin alert for unhealthy instance

        Args:
            db: Database session
            result: Health check result
        """
        alert = AdminAlert(
            alert_type="instance_unhealthy",
            priority="high",
            title=f"Instance Unhealthy: {result.instance.flux_app_name}",
            message=f"Instance {result.instance.flux_app_name} failed {self.UNHEALTHY_THRESHOLD} consecutive health checks. Error: {result.error_message}",
            metadata={
                "instance_id": result.instance.id,
                "app_name": result.instance.flux_app_name,
                "protocol": result.instance.protocol_id,
                "country": result.instance.country_code,
                "error": result.error_message,
                "last_healthy": (
                    result.instance.last_health_check.isoformat()
                    if result.instance.last_health_check
                    else None
                ),
            },
            acknowledged=False,
        )

        db.add(alert)
        db.commit()

        logger.info(f"Created unhealthy alert for {result.instance.flux_app_name}")

    async def _create_recovery_alert(self, db: Session, instance: ProtocolInstance):
        """
        Create admin alert for recovered instance

        Args:
            db: Database session
            instance: Recovered instance
        """
        alert = AdminAlert(
            alert_type="instance_recovered",
            priority="medium",
            title=f"Instance Recovered: {instance.flux_app_name}",
            message=f"Instance {instance.flux_app_name} has recovered and is now healthy.",
            metadata={
                "instance_id": instance.id,
                "app_name": instance.flux_app_name,
                "protocol": instance.protocol_id,
                "country": instance.country_code,
            },
            acknowledged=False,
        )

        db.add(alert)
        db.commit()

        logger.info(f"Created recovery alert for {instance.flux_app_name}")

    async def _attempt_recovery(self, db: Session, instance: ProtocolInstance) -> bool:
        """
        Attempt to recover an unhealthy instance

        Args:
            db: Database session
            instance: Instance to recover

        Returns:
            True if recovery succeeded
        """
        logger.info(f"Attempting to recover {instance.flux_app_name}")

        try:
            # Try restarting the instance
            await self.flux_client.restart_app(cast(str, instance.flux_app_name))

            logger.info(f"Restarted {instance.flux_app_name}, waiting for recovery...")

            # Wait for recovery
            await asyncio.sleep(self.RECOVERY_TIMEOUT)

            # Check health again
            result = await self.check_instance_health(instance)

            if result.is_healthy:
                logger.info(f"Recovery successful for {instance.flux_app_name}")
                cast(Any, instance).is_active = True
                db.commit()
                return True
            else:
                logger.warning(f"Recovery failed for {instance.flux_app_name}")
                return False

        except Exception as e:
            logger.error(
                f"Recovery attempt failed for {instance.flux_app_name}: {str(e)}"
            )
            return False

    async def get_instance_metrics(
        self,
        instance: ProtocolInstance,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> Dict:
        """
        Get performance metrics for an instance

        Args:
            instance: ProtocolInstance to get metrics for
            start_time: Metrics start time (default: 24 hours ago)
            end_time: Metrics end time (default: now)

        Returns:
            Dictionary of performance metrics
        """
        if not start_time:
            start_time = datetime.now() - timedelta(hours=24)

        if not end_time:
            end_time = datetime.now()

        try:
            metrics_fetcher = getattr(self.flux_client, "get_app_metrics", None)
            if not callable(metrics_fetcher):
                logger.warning("Flux client does not support get_app_metrics")
                return {}

            metrics_response = await metrics_fetcher(
                instance.flux_app_name, start_time=start_time, end_time=end_time
            )

            return metrics_response.get("metrics", {})

        except FluxCloudAPIException as e:
            logger.error(
                f"Failed to get metrics for {instance.flux_app_name}: {str(e)}"
            )
            return {}

    async def get_overall_health_status(self, db: Session) -> Dict:
        """
        Get overall health status across all instances

        Args:
            db: Database session

        Returns:
            Dictionary with overall health statistics
        """
        all_instances = db.query(ProtocolInstance).all()
        active_instances = [i for i in all_instances if i.is_active]

        # Calculate uptime statistics
        total_instances = len(all_instances)
        active_count = len(active_instances)
        inactive_count = total_instances - active_count

        # Check recent health checks
        recent_threshold = datetime.now() - timedelta(
            minutes=self.HEALTH_CHECK_INTERVAL
        )
        recently_checked = sum(
            1
            for i in active_instances
            if i.last_health_check and i.last_health_check > recent_threshold
        )

        # Calculate health percentage
        health_percentage = (
            (active_count / total_instances * 100) if total_instances > 0 else 0
        )

        return {
            "total_instances": total_instances,
            "active_instances": active_count,
            "inactive_instances": inactive_count,
            "health_percentage": round(health_percentage, 2),
            "recently_checked": recently_checked,
            "last_check_interval_minutes": self.HEALTH_CHECK_INTERVAL / 60,
            "status": (
                "healthy"
                if health_percentage >= 95
                else "degraded"
                if health_percentage >= 80
                else "unhealthy"
            ),
        }

    async def start_monitoring(self, db: Session, interval: Optional[int] = None):
        """
        Start continuous health monitoring

        Args:
            db: Database session
            interval: Check interval in seconds (default: HEALTH_CHECK_INTERVAL)
        """
        interval = interval or self.HEALTH_CHECK_INTERVAL

        logger.info(f"Starting health monitoring (interval: {interval}s)")

        while True:
            try:
                await self.check_all_instances(db)
                await asyncio.sleep(interval)

            except Exception as e:
                logger.error(f"Error in health monitoring loop: {str(e)}")
                await asyncio.sleep(60)  # Wait 1 minute before retrying

    async def close(self):
        """Close the FluxCloud client connection"""
        await self.flux_client.close()
