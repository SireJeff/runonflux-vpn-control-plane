"""
Celery tasks for FluxCloud infrastructure management
Background tasks for monitoring and maintaining VPN nodes
"""

import asyncio
import logging
from datetime import datetime
from typing import List

from celery import shared_task

from app.core.database import SessionLocal
from app.models import AdminAlert, Protocol, ProtocolInstance
from app.services.flux import FluxCloudClient, FluxHealthMonitor, FluxNodeManager

logger = logging.getLogger(__name__)


@shared_task(name="flux.check_all_instances_health")
def check_all_instances_health():
    """Acknowledge old queued jobs; FDM now owns endpoint-health decisions.

    The legacy monitor compared the Flux API envelope's status ("success") to
    "healthy", and queried synthetic "fdm-discovered" rows as app names. Its
    verdict was not an endpoint probe. Keep this task name during retirement so
    old beat messages cannot restart that writer or fail as unregistered tasks.
    """
    logger.info("Skipping retired flux.check_all_instances_health task")
    return {"skipped": "retired", "replacement": "fdm.sync_all_deployments"}


@shared_task(name="flux.monitor_instance_metrics")
def monitor_instance_metrics(instance_id: int):
    """
    Monitor metrics for a specific instance

    Args:
        instance_id: ProtocolInstance ID to monitor
    """
    logger.info(f"Monitoring metrics for instance {instance_id}")

    db = SessionLocal()

    try:
        instance = db.query(ProtocolInstance).get(instance_id)

        if not instance:
            logger.error(f"Instance {instance_id} not found")
            return {"error": "Instance not found"}

        loop = asyncio.get_event_loop()
        if loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        async def get_metrics():
            async with FluxHealthMonitor() as monitor:
                metrics = await monitor.get_instance_metrics(instance)
                return metrics

        metrics = loop.run_until_complete(get_metrics())

        logger.info(f"Retrieved metrics for {instance.flux_app_name}")

        return {
            "instance_id": instance_id,
            "app_name": instance.flux_app_name,
            "metrics": metrics,
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"Error monitoring instance {instance_id}: {str(e)}")
        raise

    finally:
        db.close()


@shared_task(name="flux.restart_unhealthy_instances")
def restart_unhealthy_instances():
    """Drain legacy restart jobs without undoing FDM or operator deactivation.

    Inactive PI rows include retired IPs and deliberately demoted endpoints;
    they are not a list of apps that should be restarted. FDM probes for recovery.
    """
    logger.info("Skipping retired flux.restart_unhealthy_instances task")
    return {"skipped": "retired", "replacement": "fdm.sync_all_deployments"}


@shared_task(name="flux.deploy_protocol_instances")
def deploy_protocol_instances(protocol_id: int, instance_count: int = 40):
    """
    Deploy instances for a protocol

    Args:
        protocol_id: Protocol ID to deploy
        instance_count: Number of instances to deploy (default: 40)
    """
    logger.info(f"Deploying {instance_count} instances for protocol {protocol_id}")

    db = SessionLocal()

    try:
        protocol = db.query(Protocol).get(protocol_id)

        if not protocol:
            logger.error(f"Protocol {protocol_id} not found")
            return {"error": "Protocol not found"}

        loop = asyncio.get_event_loop()
        if loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        async def deploy():
            async with FluxNodeManager() as manager:
                instances = await manager.deploy_protocol_instances(
                    db=db, protocol=protocol, count=instance_count
                )
                return instances

        instances = loop.run_until_complete(deploy())

        logger.info(
            f"Successfully deployed {len(instances)} instances for {protocol.name}"
        )

        return {
            "protocol_id": protocol_id,
            "protocol_name": protocol.name,
            "instances_deployed": len(instances),
            "instance_ids": [i.id for i in instances],
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"Error deploying protocol instances: {str(e)}")
        raise

    finally:
        db.close()


@shared_task(name="flux.scale_protocol")
def scale_protocol(protocol_id: int, target_count: int):
    """
    Scale a protocol to target instance count

    Args:
        protocol_id: Protocol ID to scale
        target_count: Target number of instances
    """
    logger.info(f"Scaling protocol {protocol_id} to {target_count} instances")

    db = SessionLocal()

    try:
        protocol = db.query(Protocol).get(protocol_id)

        if not protocol:
            logger.error(f"Protocol {protocol_id} not found")
            return {"error": "Protocol not found"}

        loop = asyncio.get_event_loop()
        if loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        async def scale():
            async with FluxNodeManager() as manager:
                added, removed = await manager.scale_protocol(
                    db=db, protocol=protocol, target_count=target_count
                )
                return added, removed

        added, removed = loop.run_until_complete(scale())

        logger.info(
            f"Scaling complete: +{len(added)} instances, -{len(removed)} instances"
        )

        return {
            "protocol_id": protocol_id,
            "protocol_name": protocol.name,
            "instances_added": len(added),
            "instances_removed": len(removed),
            "new_total": target_count,
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"Error scaling protocol: {str(e)}")
        raise

    finally:
        db.close()


@shared_task(name="flux.get_deployment_costs")
def get_deployment_costs():
    """
    Calculate deployment costs for all protocols
    Runs daily
    """
    logger.info("Calculating deployment costs")

    db = SessionLocal()

    try:
        protocols = db.query(Protocol).filter_by(is_active=True).all()

        costs = {}

        loop = asyncio.get_event_loop()
        if loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        async def calculate_costs():
            async with FluxNodeManager() as manager:
                for protocol in protocols:
                    # Count active instances
                    active_count = (
                        db.query(ProtocolInstance)
                        .filter_by(protocol_id=protocol.id, is_active=True)
                        .count()
                    )

                    # Estimate cost
                    cost = await manager.estimate_deployment_cost(
                        protocol.name, active_count
                    )

                    costs[protocol.name] = {
                        "instance_count": active_count,
                        "monthly_cost_usd": float(cost),
                        "protocol_id": protocol.id,
                    }

        loop.run_until_complete(calculate_costs())

        total_cost = sum(c["monthly_cost_usd"] for c in costs.values())

        logger.info(f"Total estimated monthly cost: ${total_cost}")

        return {
            "protocols": costs,
            "total_monthly_cost_usd": total_cost,
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"Error calculating costs: {str(e)}")
        raise

    finally:
        db.close()


@shared_task(name="flux.cleanup_old_alerts")
def cleanup_old_alerts(days_old: int = 30):
    """
    Clean up old acknowledged alerts

    Args:
        days_old: Delete alerts older than this many days (default: 30)
    """
    logger.info(f"Cleaning up alerts older than {days_old} days")

    db = SessionLocal()

    try:
        from datetime import timedelta

        cutoff_date = datetime.now() - timedelta(days=days_old)

        # Delete old acknowledged alerts
        deleted_count = (
            db.query(AdminAlert)
            .filter(
                AdminAlert.acknowledged == True,
                AdminAlert.acknowledged_at < cutoff_date,
            )
            .delete()
        )

        db.commit()

        logger.info(f"Deleted {deleted_count} old alerts")

        return {
            "deleted_count": deleted_count,
            "cutoff_date": cutoff_date.isoformat(),
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"Error cleaning up alerts: {str(e)}")
        db.rollback()
        raise

    finally:
        db.close()


@shared_task(name="flux.generate_health_report")
def generate_health_report():
    """
    Generate overall health report
    Runs every hour
    """
    logger.info("Generating health report")

    db = SessionLocal()

    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        async def get_report():
            async with FluxHealthMonitor() as monitor:
                status = await monitor.get_overall_health_status(db)
                return status

        status = loop.run_until_complete(get_report())

        logger.info(
            f"Health report: {status['health_percentage']}% healthy ({status['status']})"
        )

        # Create alert if health is degraded
        if status["status"] in ["degraded", "unhealthy"]:
            alert = AdminAlert(
                alert_type="system_health_degraded",
                priority="high" if status["status"] == "unhealthy" else "medium",
                title=f"System Health {status['status'].capitalize()}",
                message=f"System health is {status['status']}: {status['health_percentage']}% instances healthy ({status['active_instances']}/{status['total_instances']} active)",
                metadata=status,
                acknowledged=False,
            )

            db.add(alert)
            db.commit()

        return status

    except Exception as e:
        logger.error(f"Error generating health report: {str(e)}")
        raise

    finally:
        db.close()
