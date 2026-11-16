"""
Usage Tracking Celery Tasks

Background tasks for:
- Data usage monitoring
- Usage alerts
- Connection logging
- Bandwidth tracking
"""

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List

import requests
from celery import shared_task
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models import (
    AdminAlert,
    BandwidthTimeSeries,
    ConnectionLog,
    ConnectionViolation,
    Credential,
    Protocol,
    ProtocolDailySummary,
    ProtocolInstance,
    Subscription,
    UsageAlert,
    UsageMetricDaily,
    User,
    UserProtocolAssignment,
)
from app.services.notifications.client import send_notification_sync
from app.services.usage import (
    UsageAdapterError,
    collect_live_connection_counts,
    fallback_connection_counts_from_logs,
    resolve_usage_adapter,
    upsert_daily_usage_metrics,
    upsert_hourly_usage_metrics,
)

logger = logging.getLogger(__name__)

USAGE_THRESHOLDS = [50, 80, 90, 100]


def _build_usage_alert_message(
    subscription_id: int, threshold: int, usage_gb: float, limit_gb: int
) -> str:
    return (
        f"Usage alert for subscription #{subscription_id}: "
        f"{threshold}% threshold reached ({usage_gb:.2f}GB / {limit_gb}GB)."
    )


def _write_usage_audit(
    db: Session, user_id: int, threshold: int, usage_gb: float, limit_gb: int
) -> None:
    severity = (
        "critical" if threshold == 100 else "high" if threshold >= 90 else "medium"
    )
    db.add(
        AdminAlert(
            alert_type="usage_threshold",
            priority=severity,
            title=f"Usage threshold reached: {threshold}%",
            message=(
                f"User {user_id} reached {threshold}% usage "
                f"({usage_gb:.2f}GB / {limit_gb}GB)."
            ),
            acknowledged=False,
            extra_data={
                "user_id": int(user_id),
                "threshold": int(threshold),
                "usage_gb": float(round(usage_gb, 4)),
                "limit_gb": int(limit_gb),
            },
        )
    )


def _to_naive_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(tz=None).replace(tzinfo=None)


# ============================================================================
# USAGE TRACKING TASKS
# ============================================================================


@shared_task(name="usage.sync_protocol_usage")
def sync_protocol_usage():
    """
    Sync data usage from protocol instances

    Runs: Every 15 minutes

    Flow:
    1. Query each protocol instance for usage data
    2. Update connection_logs table
    3. Aggregate usage per user
    4. Check for usage limit violations
    """
    logger.info("Syncing protocol usage data")

    db = SessionLocal()

    try:
        # Get all active protocol instances
        instances = (
            db.query(ProtocolInstance)
            .filter_by(is_active=True, health_status="healthy")
            .all()
        )

        logger.info(f"Syncing usage from {len(instances)} instances")

        synced_count = 0
        total_bandwidth = 0
        touched_times: List[datetime] = []

        for instance in instances:
            try:
                protocol_name = (
                    (instance.protocol.slug if instance.protocol else None)
                    or (instance.protocol.name if instance.protocol else None)
                    or instance.component_name
                    or ""
                )
                adapter = resolve_usage_adapter(protocol_name)
                if not adapter:
                    logger.warning(
                        "No usage adapter for instance %s protocol '%s'",
                        instance.id,
                        protocol_name,
                    )
                    continue

                records = adapter.collect(instance)
                for record in records:
                    connected_at = _to_naive_utc(record.connected_at)
                    disconnected_at = (
                        _to_naive_utc(record.disconnected_at)
                        if record.disconnected_at is not None
                        else None
                    )

                    db.add(
                        ConnectionLog(
                            user_id=record.user_id,
                            protocol_id=instance.protocol_id,
                            instance_id=instance.id,
                            connected_at=connected_at,
                            disconnected_at=disconnected_at,
                            bytes_uploaded=record.bytes_uploaded,
                            bytes_downloaded=record.bytes_downloaded,
                        )
                    )
                    total_bandwidth += record.bytes_uploaded + record.bytes_downloaded
                    touched_times.append(connected_at)

                db.commit()

                synced_count += 1

            except UsageAdapterError as e:
                logger.warning(
                    "Skipping usage sync for instance %s: %s", instance.id, str(e)
                )
                db.rollback()

            except Exception as e:
                logger.error(f"Error syncing instance {instance.id}: {str(e)}")
                db.rollback()

        if touched_times:
            window_start = min(touched_times).replace(minute=0, second=0, microsecond=0)
            window_end = max(touched_times).replace(minute=0, second=0, microsecond=0)
            window_end = window_end + timedelta(hours=1)
            upsert_hourly_usage_metrics(
                db, start_time=window_start, end_time=window_end
            )
            db.commit()

        logger.info(f"Synced usage from {synced_count} instances")

        return {
            "synced": synced_count,
            "total": len(instances),
            "total_bandwidth_gb": total_bandwidth,
        }

    except Exception as e:
        logger.error(f"Usage sync failed: {str(e)}")
        return {"error": str(e)}

    finally:
        db.close()


@shared_task(name="usage.check_usage_thresholds")
def check_usage_thresholds():
    """
    Check for usage threshold violations and send alerts

    Runs: Hourly

    Alerts at:
    - 50% usage
    - 80% usage
    - 90% usage
    - 100% usage (limit reached)
    """
    logger.info("Checking usage thresholds")

    db = SessionLocal()

    try:
        # Get active subscriptions
        subscriptions = db.query(Subscription).filter_by(is_active=True).all()

        logger.info(f"Checking usage for {len(subscriptions)} active subscriptions")

        alerts_sent = {"50%": 0, "80%": 0, "90%": 0, "100%": 0}

        for subscription in subscriptions:
            try:
                # Calculate usage for this subscription
                # Get all credential protocols assigned to subscription
                credentials = (
                    db.query(Credential)
                    .filter_by(subscription_id=subscription.id)
                    .all()
                )

                if not credentials:
                    continue

                protocol_ids = list({c.protocol_id for c in credentials})
                if not protocol_ids:
                    continue

                # Sum 30d usage via persisted daily metrics
                thirty_days_ago = datetime.now(timezone.utc).replace(
                    tzinfo=None
                ) - timedelta(days=30)
                thirty_days_ago_date = thirty_days_ago.date()

                total_usage = (
                    db.query(
                        func.sum(
                            UsageMetricDaily.bytes_uploaded
                            + UsageMetricDaily.bytes_downloaded
                        )
                    )
                    .filter(
                        UsageMetricDaily.user_id == subscription.user_id,
                        UsageMetricDaily.protocol_id.in_(protocol_ids),
                        UsageMetricDaily.usage_date >= thirty_days_ago_date,
                    )
                    .scalar()
                    or 0
                )

                # Convert to GB
                usage_gb = total_usage / (1024**3)

                if not subscription.plan or not subscription.plan.data_limit_gb:
                    continue

                limit_gb = subscription.plan.data_limit_gb
                usage_percent = (usage_gb / limit_gb) * 100

                # Check thresholds
                sent_thresholds = {
                    threshold
                    for (threshold,) in db.query(UsageAlert.threshold_percent)
                    .filter(UsageAlert.subscription_id == subscription.id)
                    .all()
                }

                for threshold in USAGE_THRESHOLDS:
                    if usage_percent < threshold or threshold in sent_thresholds:
                        continue

                    alerts_sent[f"{threshold}%"] += 1
                    db.add(
                        UsageAlert(
                            user_id=subscription.user_id,
                            subscription_id=subscription.id,
                            threshold_percent=threshold,
                            data_limit_gb=int(limit_gb),
                            data_used_gb=Decimal(str(round(usage_gb, 2))),
                        )
                    )
                    _write_usage_audit(
                        db,
                        user_id=subscription.user_id,
                        threshold=threshold,
                        usage_gb=usage_gb,
                        limit_gb=int(limit_gb),
                    )
                    send_notification_sync(
                        user_id=subscription.user_id,
                        message=_build_usage_alert_message(
                            subscription_id=subscription.id,
                            threshold=threshold,
                            usage_gb=usage_gb,
                            limit_gb=int(limit_gb),
                        ),
                    )

                    if threshold == 100 and subscription.is_active:
                        subscription.is_active = False
                        subscription.status = "expired"
                        db.add(
                            AdminAlert(
                                alert_type="usage_enforcement",
                                priority="critical",
                                title="Subscription disabled at hard usage limit",
                                message=(
                                    f"Subscription {subscription.id} for user {subscription.user_id} "
                                    "was disabled after reaching 100% usage."
                                ),
                                acknowledged=False,
                                extra_data={
                                    "subscription_id": subscription.id,
                                    "user_id": subscription.user_id,
                                },
                            )
                        )

                db.commit()

            except Exception as e:
                logger.error(
                    f"Error checking usage for subscription {subscription.id}: {str(e)}"
                )
                db.rollback()

        logger.info(f"Usage alerts sent: {alerts_sent}")

        return {"alerts_sent": alerts_sent, "total_checked": len(subscriptions)}

    except Exception as e:
        logger.error(f"Usage threshold check failed: {str(e)}")
        return {"error": str(e)}

    finally:
        db.close()


@shared_task(name="usage.aggregate_daily_usage")
def aggregate_daily_usage():
    """
    Aggregate daily usage statistics

    Runs: Daily at 2 AM

    Creates daily usage summaries for analytics
    """
    logger.info("Aggregating daily usage")

    db = SessionLocal()

    try:
        yesterday = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1)
        target_date = yesterday.date()

        upserted_rows = upsert_daily_usage_metrics(db, usage_date=target_date)
        db.commit()

        protocol_usage = (
            db.query(
                Protocol.id,
                Protocol.name,
                func.sum(UsageMetricDaily.connection_count).label("connections"),
                func.sum(UsageMetricDaily.bytes_uploaded).label("bytes_uploaded"),
                func.sum(UsageMetricDaily.bytes_downloaded).label("bytes_downloaded"),
                func.count(UsageMetricDaily.user_id.distinct()).label("unique_users"),
            )
            .join(UsageMetricDaily, UsageMetricDaily.protocol_id == Protocol.id)
            .filter(UsageMetricDaily.usage_date == target_date)
            .group_by(Protocol.id, Protocol.name)
            .all()
        )

        usage_summary = {}

        for (
            protocol_id,
            protocol_name,
            connections,
            bytes_uploaded,
            bytes_downloaded,
            unique_users,
        ) in protocol_usage:
            total_bytes = (bytes_uploaded or 0) + (bytes_downloaded or 0)
            usage_summary[protocol_name] = {
                "connections": connections,
                "bandwidth_gb": total_bytes / (1024**3),
            }

            # Persist protocol-level daily summary (upsert)
            existing = (
                db.query(ProtocolDailySummary)
                .filter(
                    ProtocolDailySummary.protocol_id == protocol_id,
                    ProtocolDailySummary.summary_date == target_date,
                )
                .first()
            )
            if existing:
                existing.total_bytes_uploaded = bytes_uploaded or 0
                existing.total_bytes_downloaded = bytes_downloaded or 0
                existing.total_connections = connections or 0
                existing.unique_users = unique_users or 0
            else:
                db.add(
                    ProtocolDailySummary(
                        protocol_id=protocol_id,
                        summary_date=target_date,
                        total_bytes_uploaded=bytes_uploaded or 0,
                        total_bytes_downloaded=bytes_downloaded or 0,
                        total_connections=connections or 0,
                        unique_users=unique_users or 0,
                    )
                )

        db.commit()

        logger.info(f"Daily usage aggregated: {usage_summary}")

        return {
            "date": target_date.isoformat(),
            "usage_by_protocol": usage_summary,
            "upserted_rows": upserted_rows,
        }

    except Exception as e:
        logger.error(f"Daily usage aggregation failed: {str(e)}")
        return {"error": str(e)}

    finally:
        db.close()


# ============================================================================
# CONNECTION MONITORING
# ============================================================================


def _terminate_user_sessions(user_id: int, db: Session) -> int:
    """Terminate a user's active sessions via container telemetry endpoints.

    Looks up the user's protocol instance assignments, then calls the
    /internal/terminate endpoint on each instance's telemetry sidecar
    (port 9090).

    Returns the number of instances where termination was attempted.
    """
    assignments = (
        db.query(UserProtocolAssignment)
        .filter(UserProtocolAssignment.user_id == user_id)
        .all()
    )

    if not assignments:
        logger.warning(
            "No instance assignments found for user %d; cannot terminate sessions",
            user_id,
        )
        return 0

    terminated = 0
    for assignment in assignments:
        instance_ip = (
            str(assignment.instance.ip_address)
            if assignment.instance and assignment.instance.ip_address
            else None
        )
        if not instance_ip:
            logger.warning(
                "Skipping instance %d for user %d: no IP address",
                assignment.instance_id,
                user_id,
            )
            continue

        try:
            response = requests.post(
                f"http://{instance_ip}:9090/internal/terminate",
                json={"user_id": str(user_id), "protocol": "auto"},
                timeout=10,
            )
            response.raise_for_status()
            logger.info(
                "Terminated sessions for user %d on instance %s (%s)",
                user_id,
                assignment.instance_id,
                instance_ip,
            )
            terminated += 1
        except requests.exceptions.Timeout:
            logger.error(
                "Timeout terminating sessions for user %d on %s",
                user_id,
                instance_ip,
            )
        except requests.exceptions.RequestException as e:
            logger.error(
                "Failed to terminate sessions for user %d on %s: %s",
                user_id,
                instance_ip,
                e,
            )

    return terminated


@shared_task(name="usage.monitor_concurrent_connections")
def monitor_concurrent_connections():
    """
    Monitor concurrent connections per user

    Runs: Every 5 minutes

    Flow:
    1. Check active connections per user
    2. Enforce connection limits by tier
    3. Send violation alerts
    """
    logger.info("Monitoring concurrent connections")

    db = SessionLocal()

    try:
        tier_limits = {"free": 1, "bronze": 2, "silver": 3, "gold": 5, "platinum": 10}

        instances = (
            db.query(ProtocolInstance)
            .filter_by(is_active=True, health_status="healthy")
            .all()
        )

        (
            live_totals,
            failed_instance_ids,
            telemetry_instances,
        ) = collect_live_connection_counts(instances)
        fallback_totals = fallback_connection_counts_from_logs(db, failed_instance_ids)
        for user_id, count in fallback_totals.items():
            live_totals[user_id] = max(live_totals.get(user_id, 0), count)

        active_connections = list(live_totals.items())

        violations = 0
        blocked = 0
        warnings = 0
        fallbacks_used = len(failed_instance_ids)

        for user_id, connection_count in active_connections:
            try:
                # Get user's active subscription
                subscription = (
                    db.query(Subscription)
                    .filter_by(user_id=user_id, is_active=True)
                    .order_by(Subscription.created_at.desc())
                    .first()
                )

                if not subscription:
                    continue

                plan = subscription.plan
                tier = plan.tier if plan and plan.tier else "bronze"
                limit = (
                    plan.max_connections
                    if plan and plan.max_connections
                    else tier_limits.get(tier, 2)
                )

                if connection_count > limit:
                    logger.warning(
                        "User %s exceeded connection limit: %s/%s",
                        user_id,
                        connection_count,
                        limit,
                    )
                    violations += 1

                    last_warning = (
                        db.query(ConnectionViolation)
                        .filter(
                            ConnectionViolation.user_id == user_id,
                            ConnectionViolation.subscription_id == subscription.id,
                            ConnectionViolation.action_taken == "warning",
                            ConnectionViolation.violation_time
                            >= datetime.now(timezone.utc).replace(tzinfo=None)
                            - timedelta(minutes=15),
                        )
                        .order_by(ConnectionViolation.violation_time.desc())
                        .first()
                    )

                    action = (
                        "blocked"
                        if (connection_count >= limit + 2 or last_warning is not None)
                        else "warning"
                    )
                    violation_protocol_id = (
                        subscription.credentials[0].protocol_id
                        if subscription.credentials
                        else None
                    )
                    if not violation_protocol_id:
                        logger.warning(
                            "Skipping violation record for user %s: no protocol assignment",
                            user_id,
                        )
                        continue

                    db.add(
                        ConnectionViolation(
                            user_id=user_id,
                            subscription_id=subscription.id,
                            protocol_id=violation_protocol_id,
                            max_allowed=limit,
                            attempted_connections=connection_count,
                            action_taken=action,
                        )
                    )

                    send_notification_sync(
                        user_id=user_id,
                        message=(
                            f"Connection limit reached: {connection_count}/{limit}. "
                            f"Action: {action}."
                        ),
                    )

                    if action == "blocked":
                        blocked += 1
                        terminated = _terminate_user_sessions(user_id, db)
                        db.add(
                            AdminAlert(
                                alert_type="connection_limit_enforcement",
                                priority="high",
                                title="Concurrent connection limit enforced",
                                message=(
                                    f"User {user_id} exceeded concurrent connection limit "
                                    f"({connection_count}/{limit}). Sessions terminated on "
                                    f"{terminated} instance(s)."
                                ),
                                acknowledged=False,
                                extra_data={
                                    "user_id": user_id,
                                    "subscription_id": subscription.id,
                                    "connections": connection_count,
                                    "limit": limit,
                                    "action": action,
                                    "terminated_instances": terminated,
                                },
                            )
                        )
                    else:
                        warnings += 1

                    db.commit()

            except Exception as e:
                logger.error(f"Error checking connections for user {user_id}: {str(e)}")
                db.rollback()

        logger.info(f"Connection monitoring complete: {violations} violations")

        return {
            "violations": violations,
            "warnings": warnings,
            "blocked": blocked,
            "total_checked": len(active_connections),
            "telemetry_instances": telemetry_instances,
            "fallback_instances": fallbacks_used,
        }

    except Exception as e:
        logger.error(f"Connection monitoring failed: {str(e)}")
        return {"error": str(e)}

    finally:
        db.close()


@shared_task(name="usage.cleanup_old_logs")
def cleanup_old_logs():
    """
    Cleanup old connection logs (7-day retention)

    Runs: Daily at 3 AM

    Privacy feature: No browsing history retained
    """
    logger.info("Cleaning up old connection logs")

    db = SessionLocal()

    try:
        # Delete logs older than 7 days
        seven_days_ago = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
            days=7
        )

        deleted = (
            db.query(ConnectionLog)
            .filter(ConnectionLog.connected_at < seven_days_ago)
            .delete()
        )

        db.commit()

        logger.info(f"Deleted {deleted} old connection logs")

        return {"deleted": deleted, "retention_days": 7}

    except Exception as e:
        logger.error(f"Log cleanup failed: {str(e)}")
        db.rollback()
        return {"error": str(e)}

    finally:
        db.close()


# ============================================================================
# BANDWIDTH ANALYTICS
# ============================================================================


@shared_task(name="usage.calculate_bandwidth_stats")
def calculate_bandwidth_stats():
    """
    Calculate bandwidth statistics for admin dashboard

    Runs: Hourly

    Provides:
    - Total bandwidth used (last hour, day, week, month)
    - Per-protocol bandwidth
    - Per-country bandwidth
    - Top users by bandwidth
    """
    logger.info("Calculating bandwidth statistics")

    db = SessionLocal()

    try:
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        time_periods = {
            "last_hour": now - timedelta(hours=1),
            "last_day": now - timedelta(days=1),
            "last_week": now - timedelta(weeks=1),
            "last_month": now - timedelta(days=30),
        }

        stats = {}

        for period_name, start_time in time_periods.items():
            total_bandwidth = (
                db.query(
                    func.sum(
                        ConnectionLog.bytes_uploaded + ConnectionLog.bytes_downloaded
                    )
                )
                .filter(ConnectionLog.connected_at >= start_time)
                .scalar()
                or 0
            )

            stats[period_name] = {
                "total_gb": total_bandwidth / (1024**3),
                "total_bytes": total_bandwidth,
            }

        logger.info(f"Bandwidth stats: {stats}")

        # Persist bandwidth time-series entries (upsert per period_type + period_start)
        for period_name, start_time in time_periods.items():
            uploaded = (
                db.query(func.sum(ConnectionLog.bytes_uploaded))
                .filter(ConnectionLog.connected_at >= start_time)
                .scalar()
                or 0
            )
            downloaded = (
                db.query(func.sum(ConnectionLog.bytes_downloaded))
                .filter(ConnectionLog.connected_at >= start_time)
                .scalar()
                or 0
            )
            total = uploaded + downloaded

            existing = (
                db.query(BandwidthTimeSeries)
                .filter(
                    BandwidthTimeSeries.period_type == period_name,
                    BandwidthTimeSeries.period_start == start_time,
                )
                .first()
            )
            if existing:
                existing.total_bytes_uploaded = uploaded
                existing.total_bytes_downloaded = downloaded
                existing.total_bytes = total
            else:
                db.add(
                    BandwidthTimeSeries(
                        period_type=period_name,
                        period_start=start_time,
                        total_bytes_uploaded=uploaded,
                        total_bytes_downloaded=downloaded,
                        total_bytes=total,
                    )
                )

        db.commit()

        # Check for unusual bandwidth spikes
        if stats["last_hour"]["total_gb"] > 100:  # Alert if > 100GB/hour
            alert = AdminAlert(
                alert_type="bandwidth_spike",
                priority="high",
                title=f"High Bandwidth Usage: {stats['last_hour']['total_gb']:.2f} GB/hour",
                message="Bandwidth usage spike detected in last hour",
                acknowledged=False,
            )

            db.add(alert)
            db.commit()

        return stats

    except Exception as e:
        logger.error(f"Bandwidth stats calculation failed: {str(e)}")
        return {"error": str(e)}

    finally:
        db.close()
