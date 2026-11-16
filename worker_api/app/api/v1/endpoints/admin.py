"""
Admin Dashboard and Management endpoints
"""

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, cast

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, case, desc, extract, false, func, text
from sqlalchemy.orm import Session

from app.core.auth import get_current_admin_user
from app.core.database import get_db
from app.models import (
    AdminAlert,
    AuthLog,
    ConnectionLog,
    Credential,
    IPChangeRequest,
    Protocol,
    ProtocolInstance,
    Subscription,
    SupportTicket,
    SystemSettings,
    User,
    UserProtocolAssignment,
    WalletTransaction,
)

try:
    from app.models.usage_analytics import BandwidthTimeSeries, ProtocolDailySummary
except ImportError:
    BandwidthTimeSeries = None  # type: ignore[assignment, misc]
    ProtocolDailySummary = None  # type: ignore[assignment, misc]
from app.schemas import SuccessResponse
from app.services.monitoring import admin_health_metrics

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["Admin"])


def _as_decimal(value: object) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


# ============================================================================
# REQUEST/RESPONSE SCHEMAS
# ============================================================================


class DashboardStats(BaseModel):
    """Overall dashboard statistics"""

    # User stats
    total_users: int
    active_users: int  # Users with active subscriptions
    new_users_today: int
    new_users_this_month: int

    # Subscription stats
    total_subscriptions: int
    active_subscriptions: int
    trial_subscriptions: int
    expiring_soon: int  # Expiring in next 7 days

    # Revenue stats
    total_revenue: Decimal
    revenue_today: Decimal
    revenue_this_month: Decimal
    avg_revenue_per_user: Decimal

    # Infrastructure stats
    total_instances: int
    healthy_instances: int
    unhealthy_instances: int
    total_countries: int

    # Support stats
    open_tickets: int
    unassigned_tickets: int
    avg_resolution_hours: Optional[float]


class RevenueAnalytics(BaseModel):
    """Revenue analytics"""

    period: str  # daily, weekly, monthly
    data: List[
        Dict[str, Any]
    ]  # [{"date": "2024-01-01", "revenue": 1000, "transactions": 50}]
    total_revenue: Decimal
    avg_transaction: Decimal
    growth_percentage: Optional[float]


class UserGrowthAnalytics(BaseModel):
    """User growth analytics"""

    period: str
    data: List[
        Dict[str, Any]
    ]  # [{"date": "2024-01-01", "new_users": 10, "total_users": 100}]
    total_new_users: int
    growth_rate: Optional[float]


class ProtocolStats(BaseModel):
    """Protocol usage statistics"""

    protocol_id: int
    protocol_name: str
    active_subscriptions: int
    total_subscriptions: int
    revenue: Decimal
    active_instances: int
    avg_health_score: float
    popularity_rank: int


class CountryStats(BaseModel):
    """Country-wise statistics"""

    country_code: str
    country_name: str
    active_instances: int
    total_connections: int
    avg_health: float


class TopUser(BaseModel):
    """Top user statistics"""

    user_id: int
    username: Optional[str]
    total_spent: Decimal
    active_subscriptions: int
    referrals: int
    joined_date: datetime


class SystemHealth(BaseModel):
    """System health metrics"""

    overall_health: float  # 0-100
    database_status: str
    redis_status: str
    celery_status: str
    api_uptime_hours: float
    total_requests_today: int
    avg_response_time_ms: float


class AlertStats(BaseModel):
    """Admin alert statistics"""

    total_alerts: int
    unacknowledged: int
    critical: int
    warning: int
    info: int
    recent_alerts: List[Dict[str, Any]]


# ============================================================================
# DASHBOARD OVERVIEW
# ============================================================================


@router.get("/dashboard", response_model=DashboardStats)
async def get_dashboard_stats(
    admin: "User" = Depends(get_current_admin_user), db: Session = Depends(get_db)
):
    """
    Get overall dashboard statistics

    Provides a comprehensive overview of the system including:
    - User metrics
    - Subscription metrics
    - Revenue metrics
    - Infrastructure health
    - Support ticket status
    """
    logger.info(f"Admin {admin.id} accessing dashboard stats")

    # User stats
    total_users = db.query(User).count()

    active_users = (
        db.query(User)
        .join(Subscription)
        .filter(
            and_(
                Subscription.is_active == True,
                Subscription.expires_at
                > datetime.now(timezone.utc).replace(tzinfo=None),
            )
        )
        .distinct()
        .count()
    )

    today_start = (
        datetime.now(timezone.utc)
        .replace(tzinfo=None)
        .replace(hour=0, minute=0, second=0, microsecond=0)
    )
    new_users_today = db.query(User).filter(User.created_at >= today_start).count()

    month_start = (
        datetime.now(timezone.utc)
        .replace(tzinfo=None)
        .replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    )
    new_users_this_month = db.query(User).filter(User.created_at >= month_start).count()

    # Subscription stats
    total_subscriptions = db.query(Subscription).count()

    active_subscriptions = (
        db.query(Subscription)
        .filter(
            and_(
                Subscription.is_active == True,
                Subscription.expires_at
                > datetime.now(timezone.utc).replace(tzinfo=None),
            )
        )
        .count()
    )

    trial_subscriptions = (
        db.query(Subscription)
        .filter(and_(Subscription.is_trial == True, Subscription.is_active == True))
        .count()
    )

    seven_days = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=7)
    expiring_soon = (
        db.query(Subscription)
        .filter(
            and_(
                Subscription.is_active == True,
                Subscription.expires_at.between(
                    datetime.now(timezone.utc).replace(tzinfo=None), seven_days
                ),
            )
        )
        .count()
    )

    # Revenue stats
    total_revenue_result = (
        db.query(func.sum(WalletTransaction.amount_usd))
        .filter(WalletTransaction.transaction_type == "purchase")
        .scalar()
    )
    total_revenue = (
        abs(total_revenue_result) if total_revenue_result else Decimal("0.00")
    )

    revenue_today_result = (
        db.query(func.sum(WalletTransaction.amount_usd))
        .filter(
            and_(
                WalletTransaction.transaction_type == "purchase",
                WalletTransaction.created_at >= today_start,
            )
        )
        .scalar()
    )
    revenue_today = (
        abs(revenue_today_result) if revenue_today_result else Decimal("0.00")
    )

    revenue_month_result = (
        db.query(func.sum(WalletTransaction.amount_usd))
        .filter(
            and_(
                WalletTransaction.transaction_type == "purchase",
                WalletTransaction.created_at >= month_start,
            )
        )
        .scalar()
    )
    revenue_this_month = (
        abs(revenue_month_result) if revenue_month_result else Decimal("0.00")
    )

    avg_revenue_per_user = (
        total_revenue / total_users if total_users > 0 else Decimal("0.00")
    )

    # Infrastructure stats
    total_instances = db.query(ProtocolInstance).count()
    healthy_instances = (
        db.query(ProtocolInstance)
        .filter(ProtocolInstance.health_status == "healthy")
        .count()
    )
    unhealthy_instances = total_instances - healthy_instances

    total_countries = db.query(ProtocolInstance.country_code).distinct().count()

    # Support stats
    open_tickets = (
        db.query(SupportTicket)
        .filter(SupportTicket.status.in_(["open", "in_progress", "waiting_customer"]))
        .count()
    )

    unassigned_tickets = (
        db.query(SupportTicket)
        .filter(
            and_(SupportTicket.status == "open", SupportTicket.assigned_to.is_(None))
        )
        .count()
    )

    # Average resolution time
    resolved_tickets = (
        db.query(SupportTicket).filter(SupportTicket.resolved_at.isnot(None)).all()
    )

    avg_resolution_hours = None
    if resolved_tickets:

        def _resolution_hours(ticket: SupportTicket) -> float:
            # resolved_at guaranteed by the isnot(None) filter above;
            # created_at is always populated via server_default on insert.
            resolved_at = ticket.resolved_at
            created_at = ticket.created_at
            assert resolved_at is not None
            assert created_at is not None
            return (resolved_at - created_at).total_seconds() / 3600

        total_hours = sum(_resolution_hours(ticket) for ticket in resolved_tickets)
        avg_resolution_hours = total_hours / len(resolved_tickets)

    return DashboardStats(
        total_users=total_users,
        active_users=active_users,
        new_users_today=new_users_today,
        new_users_this_month=new_users_this_month,
        total_subscriptions=total_subscriptions,
        active_subscriptions=active_subscriptions,
        trial_subscriptions=trial_subscriptions,
        expiring_soon=expiring_soon,
        total_revenue=total_revenue,
        revenue_today=revenue_today,
        revenue_this_month=revenue_this_month,
        avg_revenue_per_user=avg_revenue_per_user,
        total_instances=total_instances,
        healthy_instances=healthy_instances,
        unhealthy_instances=unhealthy_instances,
        total_countries=total_countries,
        open_tickets=open_tickets,
        unassigned_tickets=unassigned_tickets,
        avg_resolution_hours=avg_resolution_hours,
    )


# ============================================================================
# ANALYTICS
# ============================================================================


@router.get("/analytics/revenue", response_model=RevenueAnalytics)
async def get_revenue_analytics(
    admin: "User" = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
    period: str = Query(default="daily", pattern="^(daily|weekly|monthly)$"),
    days: int = Query(default=30, ge=1, le=365),
):
    """
    Get revenue analytics for specified period

    **Periods:**
    - daily: Daily revenue for last N days
    - weekly: Weekly revenue aggregated
    - monthly: Monthly revenue aggregated
    """
    logger.info(
        f"Admin {admin.id} requesting revenue analytics: {period} for {days} days"
    )

    start_date = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)

    # Get transactions
    transactions = (
        db.query(WalletTransaction)
        .filter(
            and_(
                WalletTransaction.transaction_type == "purchase",
                WalletTransaction.created_at >= start_date,
            )
        )
        .all()
    )

    # Aggregate data
    data = []
    if period == "daily":
        # Group by day
        daily_data = {}
        for txn in transactions:
            txn_created_at = txn.created_at
            # created_at is always populated via server_default on insert.
            assert txn_created_at is not None
            date_key = txn_created_at.date().isoformat()
            txn_amount = _as_decimal(txn.amount_usd).copy_abs()
            if date_key not in daily_data:
                daily_data[date_key] = {"revenue": Decimal("0.00"), "transactions": 0}
            current_revenue = cast(Decimal, daily_data[date_key]["revenue"])
            daily_data[date_key]["revenue"] = current_revenue + txn_amount
            daily_data[date_key]["transactions"] = (
                cast(int, daily_data[date_key]["transactions"]) + 1
            )

        for date_str, values in sorted(daily_data.items()):
            data.append(
                {
                    "date": date_str,
                    "revenue": float(cast(Decimal, values["revenue"])),
                    "transactions": values["transactions"],
                }
            )

    total_revenue = sum(
        (_as_decimal(txn.amount_usd).copy_abs() for txn in transactions),
        Decimal("0.00"),
    )
    avg_transaction = (
        total_revenue / len(transactions) if transactions else Decimal("0.00")
    )

    # Calculate growth (compare to previous period)
    previous_start = start_date - timedelta(days=days)
    previous_transactions = (
        db.query(WalletTransaction)
        .filter(
            and_(
                WalletTransaction.transaction_type == "purchase",
                WalletTransaction.created_at.between(previous_start, start_date),
            )
        )
        .all()
    )

    previous_revenue = sum(
        (_as_decimal(txn.amount_usd).copy_abs() for txn in previous_transactions),
        Decimal("0.00"),
    )
    growth_percentage = None
    if previous_revenue > 0:
        growth_percentage = float(
            ((total_revenue - previous_revenue) / previous_revenue) * 100
        )

    return RevenueAnalytics(
        period=period,
        data=data,
        total_revenue=total_revenue,
        avg_transaction=avg_transaction,
        growth_percentage=growth_percentage,
    )


@router.get("/analytics/users", response_model=UserGrowthAnalytics)
async def get_user_growth_analytics(
    admin: "User" = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
    period: str = Query(default="daily", pattern="^(daily|weekly|monthly)$"),
    days: int = Query(default=30, ge=1, le=365),
):
    """
    Get user growth analytics
    """
    logger.info(f"Admin {admin.id} requesting user growth analytics")

    start_date = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)

    users = db.query(User).filter(User.created_at >= start_date).all()

    # Aggregate by day
    daily_data = {}
    for user in users:
        user_created_at = user.created_at
        # created_at is always populated via server_default on insert.
        assert user_created_at is not None
        date_key = user_created_at.date().isoformat()
        if date_key not in daily_data:
            daily_data[date_key] = 0
        daily_data[date_key] += 1

    # Build cumulative data
    data = []
    cumulative = db.query(User).filter(User.created_at < start_date).count()

    for date_str, new_users in sorted(daily_data.items()):
        cumulative += new_users
        data.append(
            {"date": date_str, "new_users": new_users, "total_users": cumulative}
        )

    total_new_users = len(users)

    # Calculate growth rate
    previous_start = start_date - timedelta(days=days)
    previous_users = (
        db.query(User)
        .filter(User.created_at.between(previous_start, start_date))
        .count()
    )

    growth_rate = None
    if previous_users > 0:
        growth_rate = float(((total_new_users - previous_users) / previous_users) * 100)

    return UserGrowthAnalytics(
        period=period,
        data=data,
        total_new_users=total_new_users,
        growth_rate=growth_rate,
    )


@router.get("/analytics/protocols", response_model=List[ProtocolStats])
async def get_protocol_analytics(
    admin: "User" = Depends(get_current_admin_user), db: Session = Depends(get_db)
):
    """
    Get protocol usage statistics
    """
    protocols = db.query(Protocol).all()

    results = []
    for idx, protocol in enumerate(protocols, 1):
        # Count subscriptions
        active_subs = (
            db.query(Subscription)
            .filter(
                and_(
                    Subscription.protocol_id == protocol.id,
                    Subscription.is_active == True,
                    Subscription.expires_at
                    > datetime.now(timezone.utc).replace(tzinfo=None),
                )
            )
            .count()
        )

        total_subs = db.query(Subscription).filter_by(protocol_id=protocol.id).count()

        # Calculate revenue
        revenue_result = (
            db.query(func.sum(Subscription.price_usd))
            .filter(Subscription.protocol_id == protocol.id)
            .scalar()
        )
        revenue = revenue_result if revenue_result else Decimal("0.00")

        # Count instances
        active_instances = (
            db.query(ProtocolInstance)
            .filter(
                and_(
                    ProtocolInstance.protocol_id == protocol.id,
                    ProtocolInstance.is_active == True,
                )
            )
            .count()
        )

        # Calculate health
        instances = db.query(ProtocolInstance).filter_by(protocol_id=protocol.id).all()
        health_scores = [
            1.0 if inst.health_status == "healthy" else 0.0 for inst in instances
        ]
        avg_health = sum(health_scores) / len(health_scores) if health_scores else 0.0

        results.append(
            ProtocolStats(
                protocol_id=protocol.id,
                protocol_name=protocol.name,
                active_subscriptions=active_subs,
                total_subscriptions=total_subs,
                revenue=revenue,
                active_instances=active_instances,
                avg_health_score=avg_health * 100,
                popularity_rank=idx,
            )
        )

    # Sort by active subscriptions
    results.sort(key=lambda x: x.active_subscriptions, reverse=True)

    # Update popularity rank
    for idx, stat in enumerate(results, 1):
        stat.popularity_rank = idx

    return results


@router.get("/analytics/countries", response_model=List[CountryStats])
async def get_country_analytics(
    admin: "User" = Depends(get_current_admin_user), db: Session = Depends(get_db)
):
    """
    Get country-wise statistics
    """
    # Get country-wise instance stats (active count and healthy count)
    # Using group_by and aggregation to avoid N+1 queries
    country_instance_stats = (
        db.query(
            ProtocolInstance.country_code,
            ProtocolInstance.country_name,
            func.sum(case((ProtocolInstance.is_active == True, 1), else_=0)).label(
                "active_instances"
            ),
            func.sum(
                case(
                    (
                        and_(
                            ProtocolInstance.is_active == True,
                            ProtocolInstance.health_status == "healthy",
                        ),
                        1,
                    ),
                    else_=0,
                )
            ).label("healthy_instances"),
        )
        .group_by(ProtocolInstance.country_code, ProtocolInstance.country_name)
        .all()
    )

    # Get assignment counts per country
    connection_counts = (
        db.query(
            ProtocolInstance.country_code,
            func.count(UserProtocolAssignment.id).label("total_connections"),
        )
        .select_from(UserProtocolAssignment)
        .join(
            ProtocolInstance, UserProtocolAssignment.instance_id == ProtocolInstance.id
        )
        .group_by(ProtocolInstance.country_code)
        .all()
    )

    # Create a lookup for connections to efficiently merge with instance stats
    connections_lookup = {
        c.country_code: c.total_connections for c in connection_counts
    }

    results = []
    for stat in country_instance_stats:
        active_count = int(stat.active_instances or 0)
        healthy_count = int(stat.healthy_instances or 0)
        total_connections = connections_lookup.get(stat.country_code, 0)

        # Calculate average health from healthy/active counts (replicates original logic)
        avg_health = (healthy_count / active_count * 100) if active_count > 0 else 0.0

        results.append(
            CountryStats(
                country_code=stat.country_code,
                country_name=stat.country_name,
                active_instances=active_count,
                total_connections=total_connections,
                avg_health=avg_health,
            )
        )

    # Sort by connections descending (preserved from original logic)
    results.sort(key=lambda x: x.total_connections, reverse=True)

    return results


@router.get("/analytics/top-users", response_model=List[TopUser])
async def get_top_users(
    admin: "User" = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
    limit: int = Query(default=10, le=100),
):
    """
    Get top users by spending
    """
    # Get users with total spending
    users = db.query(User).all()

    user_stats = []
    for user in users:
        # Calculate total spent
        total_spent_result = (
            db.query(func.sum(WalletTransaction.amount_usd))
            .filter(
                and_(
                    WalletTransaction.user_id == user.id,
                    WalletTransaction.transaction_type == "purchase",
                )
            )
            .scalar()
        )

        total_spent = abs(total_spent_result) if total_spent_result else Decimal("0.00")

        if total_spent == 0:
            continue

        # Count active subscriptions
        active_subs = (
            db.query(Subscription)
            .filter(
                and_(
                    Subscription.user_id == user.id,
                    Subscription.is_active == True,
                    Subscription.expires_at
                    > datetime.now(timezone.utc).replace(tzinfo=None),
                )
            )
            .count()
        )

        user_stats.append(
            TopUser(
                user_id=user.id,
                username=user.telegram_username,
                total_spent=total_spent,
                active_subscriptions=active_subs,
                referrals=user.total_referrals,
                joined_date=user.created_at,
            )
        )

    # Sort by total spent
    user_stats.sort(key=lambda x: x.total_spent, reverse=True)

    return user_stats[:limit]


@router.get("/analytics/usage")
async def get_usage_analytics(
    admin: "User" = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
    period: str = Query(default="daily", pattern="^(daily|weekly|monthly)$"),
    protocol_id: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
):
    """
    Get per-protocol usage analytics for the admin dashboard.

    **Periods:**
    - daily: Daily usage summaries
    - weekly: Weekly aggregated usage
    - monthly: Monthly aggregated usage

    **Filters:**
    - protocol_id: Filter by specific protocol
    - start_date / end_date: Date range filter (YYYY-MM-DD)
    """
    if ProtocolDailySummary is None:
        return {"summaries": []}

    logger.info(
        f"Admin {admin.id} requesting usage analytics: period={period}, "
        f"protocol_id={protocol_id}"
    )

    query = db.query(ProtocolDailySummary)

    if protocol_id:
        query = query.filter(ProtocolDailySummary.protocol_id == protocol_id)

    if start_date:
        try:
            start_dt = datetime.fromisoformat(start_date)
            query = query.filter(ProtocolDailySummary.date >= start_dt.date())
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid start_date format. Use ISO date (YYYY-MM-DD)",
            ) from exc

    if end_date:
        try:
            end_dt = datetime.fromisoformat(end_date)
            query = query.filter(ProtocolDailySummary.date <= end_dt.date())
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid end_date format. Use ISO date (YYYY-MM-DD)",
            ) from exc

    # Default to last 30 days if no date filters
    if not start_date and not end_date:
        thirty_days_ago = datetime.now(timezone.utc).replace(
            tzinfo=None
        ).date() - timedelta(days=30)
        query = query.filter(ProtocolDailySummary.date >= thirty_days_ago)

    query = query.order_by(ProtocolDailySummary.date.desc())
    summaries = query.all()

    results = []
    for row in summaries:
        total_gb = (
            _as_decimal(row.total_gb)
            if hasattr(row, "total_gb")
            else (_as_decimal(row.uploaded_gb) + _as_decimal(row.downloaded_gb))
        )
        results.append(
            {
                "protocol_id": row.protocol_id,
                "date": row.date.isoformat() if hasattr(row, "date") else str(row.date),
                "uploaded_gb": float(_as_decimal(row.uploaded_gb)),
                "downloaded_gb": float(_as_decimal(row.downloaded_gb)),
                "total_gb": float(total_gb),
                "connections": int(
                    row.connections if hasattr(row, "connections") else 0
                ),
                "unique_users": int(
                    (row.unique_users or 0) if hasattr(row, "unique_users") else 0
                ),
            }
        )

    return {"summaries": results}


@router.get("/analytics/bandwidth")
async def get_bandwidth_analytics(
    admin: "User" = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
    period_type: str = Query(
        default="daily", pattern="^(hourly|daily|weekly|monthly)$"
    ),
    limit: int = Query(default=24, ge=1, le=168),
):
    """
    Get bandwidth time series data for dashboard charts.

    **Period types:**
    - hourly: Hourly data points
    - daily: Daily data points (default)
    - weekly: Weekly aggregated data
    - monthly: Monthly aggregated data

    **Parameters:**
    - limit: Max number of data points (default 24, max 168)
    """
    if BandwidthTimeSeries is None:
        return {"period_type": period_type, "data": []}

    logger.info(
        f"Admin {admin.id} requesting bandwidth analytics: "
        f"period_type={period_type}, limit={limit}"
    )

    query = db.query(BandwidthTimeSeries)

    if hasattr(BandwidthTimeSeries, "period_type"):
        query = query.filter(BandwidthTimeSeries.period_type == period_type)

    query = query.order_by(
        desc(
            BandwidthTimeSeries.period_start
            if hasattr(BandwidthTimeSeries, "period_start")
            else BandwidthTimeSeries.id
        )
    ).limit(limit)

    rows = query.all()

    results = []
    for row in rows:
        total_gb = (
            _as_decimal(row.total_gb)
            if hasattr(row, "total_gb")
            else (_as_decimal(row.uploaded_gb) + _as_decimal(row.downloaded_gb))
        )
        period_start = (
            row.period_start if hasattr(row, "period_start") else row.period_start
        )
        results.append(
            {
                "period_start": (
                    period_start.isoformat()
                    if hasattr(period_start, "isoformat")
                    else str(period_start)
                ),
                "uploaded_gb": float(_as_decimal(row.uploaded_gb)),
                "downloaded_gb": float(_as_decimal(row.downloaded_gb)),
                "total_gb": float(total_gb),
            }
        )

    return {"period_type": period_type, "data": results}


# ============================================================================
# SYSTEM HEALTH
# ============================================================================


@router.get("/system/health", response_model=SystemHealth)
async def get_system_health(
    admin: "User" = Depends(get_current_admin_user), db: Session = Depends(get_db)
):
    """
    Get system health metrics
    """
    # Database status
    db_status = "connected"
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        db_status = "disconnected"

    # Redis status
    redis_status = "connected"
    try:
        from app.core.redis_client import get_redis

        redis = get_redis()
        if redis is None:
            redis_status = "disabled"
        else:
            redis.ping()
    except Exception:
        redis_status = "disconnected"

    # Celery status (simplified)
    celery_status = "disconnected"
    try:
        from celery import current_app

        current_app.control.ping()
        celery_status = "running"
    except Exception:
        celery_status = "disconnected"

    # Calculate overall health
    instance_health = (
        db.query(ProtocolInstance)
        .filter(ProtocolInstance.health_status == "healthy")
        .count()
    )
    total_instances = db.query(ProtocolInstance).count()

    overall_health = (
        (instance_health / total_instances * 100) if total_instances > 0 else 100.0
    )

    api_metrics = {
        "api_uptime_hours": 0.0,
        "total_requests_today": 0,
        "avg_response_time_ms": 0.0,
    }
    try:
        api_metrics = admin_health_metrics.get_today_metrics(db)
    except Exception as exc:
        logger.warning("Failed to load admin health telemetry: %s", str(exc))

    return SystemHealth(
        overall_health=overall_health,
        database_status=db_status,
        redis_status=redis_status,
        celery_status=celery_status,
        api_uptime_hours=api_metrics["api_uptime_hours"],
        total_requests_today=api_metrics["total_requests_today"],
        avg_response_time_ms=api_metrics["avg_response_time_ms"],
    )


# ============================================================================
# ALERTS
# ============================================================================


@router.get("/alerts", response_model=AlertStats)
async def get_admin_alerts(
    admin: "User" = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
    limit: int = Query(default=10, le=50),
):
    """
    Get admin alerts and notifications
    """
    total_alerts = db.query(AdminAlert).count()
    unacknowledged = (
        db.query(AdminAlert).filter(AdminAlert.acknowledged == False).count()
    )

    critical = db.query(AdminAlert).filter(AdminAlert.priority == "critical").count()
    warning = db.query(AdminAlert).filter(AdminAlert.priority == "high").count()
    info = (
        db.query(AdminAlert).filter(AdminAlert.priority.in_(["medium", "low"])).count()
    )

    # Get recent alerts
    recent = (
        db.query(AdminAlert).order_by(desc(AdminAlert.created_at)).limit(limit).all()
    )

    recent_alerts = [
        {
            "id": alert.id,
            "type": alert.alert_type,
            "priority": alert.priority,
            "title": alert.title,
            "message": alert.message,
            "created_at": (
                alert.created_at.isoformat() if alert.created_at is not None else None
            ),
            "acknowledged": alert.acknowledged,
        }
        for alert in recent
    ]

    return AlertStats(
        total_alerts=total_alerts,
        unacknowledged=unacknowledged,
        critical=critical,
        warning=warning,
        info=info,
        recent_alerts=recent_alerts,
    )


@router.post("/alerts/{alert_id}/acknowledge", response_model=SuccessResponse)
async def acknowledge_alert(
    alert_id: int,
    admin: "User" = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """
    Acknowledge an admin alert
    """
    alert = db.query(AdminAlert).filter_by(id=alert_id).first()

    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found"
        )

    alert_obj = cast(Any, alert)
    alert_obj.acknowledged = True
    alert_obj.acknowledged_by = admin.id
    alert_obj.acknowledged_at = datetime.now(timezone.utc).replace(tzinfo=None)

    db.commit()

    logger.info(f"Alert {alert_id} acknowledged by admin {admin.id}")

    return SuccessResponse(
        message="Alert acknowledged successfully", data={"alert_id": alert_id}
    )


# ============================================================================
# SERVER/INSTANCE MANAGEMENT ENDPOINTS
# ============================================================================


class ServerInstanceResponse(BaseModel):
    """Server instance details"""

    id: int
    protocol_id: int
    protocol_name: str
    country_code: str
    country_name: str
    public_ip: str
    port: int
    health_status: str
    last_health_check: Optional[datetime]
    is_active: bool
    active_connections: int = 0
    created_at: datetime


class ServerStatsResponse(BaseModel):
    """Server statistics"""

    total_instances: int
    healthy_instances: int
    degraded_instances: int
    unhealthy_instances: int
    total_countries: int
    total_connections: int
    avg_health_score: float


@router.get("/servers/instances", response_model=List[ServerInstanceResponse])
async def get_server_instances(
    admin: "User" = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
    protocol_id: Optional[int] = None,
    country_code: Optional[str] = None,
    health_status: Optional[str] = None,
):
    """
    Get all server instances with optional filtering
    """
    query = db.query(ProtocolInstance).join(Protocol)

    if protocol_id:
        query = query.filter(ProtocolInstance.protocol_id == protocol_id)
    if country_code:
        query = query.filter(ProtocolInstance.country_code == country_code)
    if health_status:
        query = query.filter(ProtocolInstance.health_status == health_status)

    instances = query.all()

    results = []
    for inst in instances:
        # Count active connections for this instance
        active_conns = (
            db.query(UserProtocolAssignment)
            .filter(UserProtocolAssignment.instance_id == inst.id)
            .count()
        )

        results.append(
            ServerInstanceResponse(
                id=inst.id,
                protocol_id=inst.protocol_id,
                protocol_name=inst.protocol.name,
                country_code=inst.country_code,
                country_name=inst.country_name,
                public_ip=str(inst.ip_address),
                port=inst.protocol.default_port,
                health_status=inst.health_status,
                last_health_check=inst.last_health_check,
                is_active=inst.is_active,
                active_connections=active_conns,
                created_at=inst.created_at,
            )
        )

    return results


@router.get("/servers/stats", response_model=ServerStatsResponse)
async def get_server_stats(
    admin: "User" = Depends(get_current_admin_user), db: Session = Depends(get_db)
):
    """
    Get server instance statistics
    """
    instances = db.query(ProtocolInstance).all()

    total = len(instances)
    healthy = sum(1 for i in instances if i.health_status == "healthy")
    degraded = sum(1 for i in instances if i.health_status == "degraded")
    unhealthy = sum(1 for i in instances if i.health_status == "unhealthy")

    countries = len(set(i.country_code for i in instances))

    # Count total assigned protocol connections
    total_conns = db.query(UserProtocolAssignment).count()

    # Calculate average health
    health_values = {"healthy": 100, "degraded": 50, "unhealthy": 0}
    avg_health = (
        sum(health_values.get(cast(str, i.health_status), 0) for i in instances) / total
        if total > 0
        else 0
    )

    return ServerStatsResponse(
        total_instances=total,
        healthy_instances=healthy,
        degraded_instances=degraded,
        unhealthy_instances=unhealthy,
        total_countries=countries,
        total_connections=total_conns,
        avg_health_score=avg_health,
    )


# ============================================================================
# SYSTEM LOGS ENDPOINTS
# ============================================================================


class LogEntryResponse(BaseModel):
    """System log entry"""

    id: int
    timestamp: datetime
    level: str
    source: str
    message: str
    user_id: Optional[int]
    metadata: Optional[Dict[str, Any]]


class LogStatsResponse(BaseModel):
    """Log statistics"""

    total_today: int
    errors_today: int
    warnings_today: int
    most_common_source: str


@router.get("/logs", response_model=List[LogEntryResponse])
async def get_system_logs(
    admin: "User" = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
    level: Optional[str] = None,
    source: Optional[str] = None,
    search: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = Query(default=100, le=1000),
):
    """
    Get system logs (connection logs + auth logs combined)
    """
    source = source.lower() if source else None
    search = search.lower() if search else None

    start_dt: Optional[datetime] = None
    end_dt: Optional[datetime] = None

    if start_date:
        try:
            start_dt = datetime.fromisoformat(start_date)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid start_date format. Use ISO date (YYYY-MM-DD)",
            ) from exc

    if end_date:
        try:
            end_dt = datetime.fromisoformat(end_date)
            if len(end_date) == 10:
                end_dt = end_dt + timedelta(days=1) - timedelta(microseconds=1)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid end_date format. Use ISO date (YYYY-MM-DD)",
            ) from exc

    conn_logs = []
    if source in (None, "connection"):
        conn_query = db.query(ConnectionLog)
        if start_dt:
            conn_query = conn_query.filter(ConnectionLog.connected_at >= start_dt)
        if end_dt:
            conn_query = conn_query.filter(ConnectionLog.connected_at <= end_dt)
        conn_logs = (
            conn_query.order_by(desc(ConnectionLog.connected_at)).limit(limit).all()
        )

    auth_logs = []
    if source in (None, "auth"):
        auth_query = db.query(AuthLog)
        if start_dt:
            auth_query = auth_query.filter(AuthLog.created_at >= start_dt)
        if end_dt:
            auth_query = auth_query.filter(AuthLog.created_at <= end_dt)
        if level:
            normalized_level = level.upper()
            if normalized_level == "WARNING":
                auth_query = auth_query.filter(AuthLog.success == False)
            elif normalized_level == "INFO":
                auth_query = auth_query.filter(AuthLog.success == True)
            elif normalized_level in ("ERROR", "CRITICAL", "DEBUG"):
                auth_query = auth_query.filter(false())
        auth_logs = auth_query.order_by(desc(AuthLog.created_at)).limit(limit).all()

    results = []

    # Add connection logs
    for log in conn_logs:
        results.append(
            LogEntryResponse(
                id=log.id,
                timestamp=log.connected_at,
                level="INFO",
                source="connection",
                message=f"User {log.user_id} connected (instance {log.instance_id})",
                user_id=log.user_id,
                metadata={
                    "instance_id": log.instance_id,
                    "disconnected": log.disconnected_at is not None,
                },
            )
        )

    # Add auth logs
    for auth_log in auth_logs:
        results.append(
            LogEntryResponse(
                id=auth_log.id + 100000,  # Offset to avoid ID collision
                timestamp=auth_log.created_at,
                level="INFO" if auth_log.success else "WARNING",
                source="auth",
                message=f"Auth event for user {auth_log.user_id}: {'success' if auth_log.success else 'failed'}",
                user_id=auth_log.user_id,
                metadata={"success": auth_log.success},
            )
        )

    # Sort by timestamp descending
    results.sort(key=lambda x: x.timestamp, reverse=True)

    # Apply in-memory filters
    if level:
        results = [r for r in results if r.level == level.upper()]
    if source:
        results = [r for r in results if r.source == source]
    if search:
        results = [
            r
            for r in results
            if search in r.message.lower()
            or (r.user_id is not None and search in str(r.user_id))
        ]

    return results[:limit]


@router.get("/logs/stats", response_model=LogStatsResponse)
async def get_log_stats(
    admin: "User" = Depends(get_current_admin_user), db: Session = Depends(get_db)
):
    """
    Get log statistics
    """
    today_start = (
        datetime.now(timezone.utc)
        .replace(tzinfo=None)
        .replace(hour=0, minute=0, second=0, microsecond=0)
    )

    # Count today's logs
    conn_logs_today = (
        db.query(ConnectionLog)
        .filter(ConnectionLog.connected_at >= today_start)
        .count()
    )

    auth_logs_today = (
        db.query(AuthLog).filter(AuthLog.created_at >= today_start).count()
    )

    total_today = conn_logs_today + auth_logs_today

    # Count errors (failed auth)
    errors_today = (
        db.query(AuthLog)
        .filter(and_(AuthLog.created_at >= today_start, AuthLog.success == False))
        .count()
    )

    return LogStatsResponse(
        total_today=total_today,
        errors_today=errors_today,
        warnings_today=errors_today,  # Same as errors for now
        most_common_source=(
            "connection" if conn_logs_today > auth_logs_today else "auth"
        ),
    )


# ============================================================================
# SETTINGS ENDPOINTS
# ============================================================================


class SystemSettingsResponse(BaseModel):
    """System settings"""

    trial_days: int = 3
    referral_commission_bronze: float = 5.0
    referral_commission_silver: float = 10.0
    referral_commission_gold: float = 15.0
    referral_commission_platinum: float = 20.0
    maintenance_mode: bool = False
    max_ip_changes_per_month: int = 3


class SystemSettingsUpdate(BaseModel):
    """Update system settings"""

    trial_days: Optional[int] = Field(None, ge=0, le=30)
    referral_commission_bronze: Optional[float] = Field(None, ge=0, le=100)
    referral_commission_silver: Optional[float] = Field(None, ge=0, le=100)
    referral_commission_gold: Optional[float] = Field(None, ge=0, le=100)
    referral_commission_platinum: Optional[float] = Field(None, ge=0, le=100)
    maintenance_mode: Optional[bool] = None
    max_ip_changes_per_month: Optional[int] = Field(None, ge=1, le=10)


@router.get("/settings", response_model=SystemSettingsResponse)
async def get_system_settings(
    admin: "User" = Depends(get_current_admin_user), db: Session = Depends(get_db)
):
    """Get persisted system settings."""
    settings = db.query(SystemSettings).filter(SystemSettings.id == 1).first()
    if settings is None:
        settings = SystemSettings(id=1)
        db.add(settings)
        db.commit()
        db.refresh(settings)

    return SystemSettingsResponse(
        trial_days=settings.trial_days,
        referral_commission_bronze=float(settings.referral_commission_bronze),
        referral_commission_silver=float(settings.referral_commission_silver),
        referral_commission_gold=float(settings.referral_commission_gold),
        referral_commission_platinum=float(settings.referral_commission_platinum),
        maintenance_mode=settings.maintenance_mode,
        max_ip_changes_per_month=settings.max_ip_changes_per_month,
    )


@router.put("/settings", response_model=SystemSettingsResponse)
async def update_system_settings(
    settings: SystemSettingsUpdate,
    admin: "User" = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """Update persisted system settings."""
    db_settings = db.query(SystemSettings).filter(SystemSettings.id == 1).first()
    if db_settings is None:
        db_settings = SystemSettings(id=1)
        db.add(db_settings)

    update_data = settings.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_settings, field, value)

    db.commit()
    db.refresh(db_settings)

    logger.info(f"Settings updated by admin {admin.id}: {update_data}")

    return SystemSettingsResponse(
        trial_days=db_settings.trial_days,
        referral_commission_bronze=float(db_settings.referral_commission_bronze),
        referral_commission_silver=float(db_settings.referral_commission_silver),
        referral_commission_gold=float(db_settings.referral_commission_gold),
        referral_commission_platinum=float(db_settings.referral_commission_platinum),
        maintenance_mode=db_settings.maintenance_mode,
        max_ip_changes_per_month=db_settings.max_ip_changes_per_month,
    )


# ============================================================================
# ADMIN USER MANAGEMENT ENDPOINTS
# ============================================================================


class AdminUserResponse(BaseModel):
    """Admin user details"""

    id: int
    telegram_username: Optional[str]
    email: Optional[str]
    is_admin: bool
    created_at: datetime


@router.get("/admins", response_model=List[AdminUserResponse])
async def get_admin_users(
    admin: "User" = Depends(get_current_admin_user), db: Session = Depends(get_db)
):
    """
    Get all admin users
    """
    admins = db.query(User).filter(User.is_admin == True).all()

    return [
        AdminUserResponse(
            id=user.id,
            telegram_username=user.telegram_username,
            email=user.email,
            is_admin=user.is_admin,
            created_at=user.created_at,
        )
        for user in admins
    ]


@router.post("/users/{user_id}/make-admin", response_model=SuccessResponse)
async def make_user_admin(
    user_id: int,
    admin: "User" = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """
    Grant admin privileges to a user
    """
    user = db.query(User).filter_by(id=user_id).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    if user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="User is already an admin"
        )

    cast(Any, user).is_admin = True
    db.commit()

    logger.info(f"User {user_id} granted admin privileges by admin {admin.id}")

    return SuccessResponse(
        message="User granted admin privileges", data={"user_id": user_id}
    )


@router.post("/users/{user_id}/remove-admin", response_model=SuccessResponse)
async def remove_user_admin(
    user_id: int,
    admin: "User" = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """
    Revoke admin privileges from a user
    """
    # Prevent removing admin from yourself
    if user_id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot remove admin privileges from yourself",
        )

    # Check if this is the last admin
    admin_count = db.query(User).filter(User.is_admin == True).count()
    if admin_count <= 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot remove the last admin user",
        )

    user = db.query(User).filter_by(id=user_id).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="User is not an admin"
        )

    cast(Any, user).is_admin = False
    db.commit()

    logger.info(f"User {user_id} admin privileges revoked by admin {admin.id}")

    return SuccessResponse(
        message="Admin privileges revoked", data={"user_id": user_id}
    )


# ============================================================================
# TRANSACTION MANAGEMENT ENDPOINTS
# ============================================================================


@router.get("/transactions", response_model=List[Any])
async def get_all_transactions(
    admin: "User" = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
    user_id: Optional[int] = None,
    transaction_type: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = Query(default=100, le=1000),
    offset: int = Query(default=0, ge=0),
):
    """
    Get all wallet transactions (admin only)
    """
    query = db.query(WalletTransaction)

    if user_id:
        query = query.filter(WalletTransaction.user_id == user_id)
    if transaction_type:
        query = query.filter(WalletTransaction.transaction_type == transaction_type)
    if status:
        query = query.filter(WalletTransaction.status == status)

    transactions = (
        query.order_by(desc(WalletTransaction.created_at))
        .offset(offset)
        .limit(limit)
        .all()
    )

    return transactions


@router.get("/withdrawals/pending", response_model=List[Any])
async def get_pending_withdrawals(
    admin: "User" = Depends(get_current_admin_user), db: Session = Depends(get_db)
):
    """
    Get all pending withdrawal requests
    """
    withdrawals = (
        db.query(WalletTransaction)
        .filter(
            and_(
                WalletTransaction.transaction_type == "withdrawal",
                WalletTransaction.status == "pending",
            )
        )
        .order_by(desc(WalletTransaction.created_at))
        .all()
    )

    return withdrawals


@router.post("/withdrawals/{transaction_id}/approve", response_model=SuccessResponse)
async def approve_withdrawal(
    transaction_id: int,
    admin: "User" = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """
    Approve a withdrawal request
    """
    transaction = db.query(WalletTransaction).filter_by(id=transaction_id).first()

    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")

    if transaction.transaction_type != "withdrawal":
        raise HTTPException(status_code=400, detail="Not a withdrawal transaction")

    if transaction.status != "pending":
        raise HTTPException(status_code=400, detail="Withdrawal already processed")

    cast(Any, transaction).status = "completed"
    db.commit()

    logger.info(f"Withdrawal {transaction_id} approved by admin {admin.id}")

    return SuccessResponse(message="Withdrawal approved")


@router.post("/withdrawals/{transaction_id}/reject", response_model=SuccessResponse)
async def reject_withdrawal(
    transaction_id: int,
    admin: "User" = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
    reason: str = "Rejected by admin",
):
    """
    Reject a withdrawal request
    """
    transaction = db.query(WalletTransaction).filter_by(id=transaction_id).first()

    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")

    if transaction.transaction_type != "withdrawal":
        raise HTTPException(status_code=400, detail="Not a withdrawal transaction")

    if transaction.status != "pending":
        raise HTTPException(status_code=400, detail="Withdrawal already processed")

    transaction_obj = cast(Any, transaction)
    transaction_obj.status = "failed"
    transaction_obj.description = f"{transaction.description} - {reason}"
    db.commit()

    logger.info(f"Withdrawal {transaction_id} rejected by admin {admin.id}: {reason}")

    return SuccessResponse(message="Withdrawal rejected")


# ============================================================================
# IP CHANGE MANAGEMENT (Admin view)
# ============================================================================


class AdminIPChangeStats(BaseModel):
    total_ip_changes: int
    pending_requests: int
    completed_today: int
    failed_requests: int
    success_rate: float


@router.get("/ip-stats", response_model=AdminIPChangeStats)
async def get_admin_ip_stats(
    admin: "User" = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    total = db.query(func.count(IPChangeRequest.id)).scalar() or 0
    pending = (
        db.query(func.count(IPChangeRequest.id))
        .filter(IPChangeRequest.status == "pending")
        .scalar()
        or 0
    )
    completed_today = (
        db.query(func.count(IPChangeRequest.id))
        .filter(
            IPChangeRequest.status == "completed",
            IPChangeRequest.processed_at >= func.current_date(),
        )
        .scalar()
        or 0
    )
    failed = (
        db.query(func.count(IPChangeRequest.id))
        .filter(IPChangeRequest.status.in_(["failed", "denied"]))
        .scalar()
        or 0
    )
    completed_total = (
        db.query(func.count(IPChangeRequest.id))
        .filter(IPChangeRequest.status == "completed")
        .scalar()
        or 0
    )
    success_rate = (completed_total / total * 100) if total > 0 else 0.0

    return AdminIPChangeStats(
        total_ip_changes=total,
        pending_requests=pending,
        completed_today=completed_today,
        failed_requests=failed,
        success_rate=round(success_rate, 1),
    )


@router.get("/ip-changes")
async def list_admin_ip_changes(
    admin: "User" = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(default=50, le=100),
    offset: int = Query(default=0, ge=0),
):
    query = db.query(IPChangeRequest)
    if status:
        query = query.filter(IPChangeRequest.status == status)

    requests = (
        query.order_by(IPChangeRequest.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    results = []
    for req in requests:
        old_instance = None
        new_instance = None
        if req.old_instance_id:
            old_instance = (
                db.query(ProtocolInstance).filter_by(id=req.old_instance_id).first()
            )
        if req.new_instance_id:
            new_instance = (
                db.query(ProtocolInstance).filter_by(id=req.new_instance_id).first()
            )

        credential = (
            db.query(Credential)
            .filter_by(
                user_id=req.user_id,
                subscription_id=req.subscription_id,
                protocol_id=req.protocol_id,
            )
            .order_by(Credential.id.asc())
            .first()
        )

        results.append(
            {
                "id": req.id,
                "credential_id": credential.id if credential else None,
                "user_id": req.user_id,
                "old_ip": str(old_instance.ip_address) if old_instance else None,
                "new_ip": str(new_instance.ip_address) if new_instance else None,
                "old_country": old_instance.country_code if old_instance else None,
                "new_country": new_instance.country_code if new_instance else None,
                "status": req.status,
                "requested_at": req.created_at.isoformat() if req.created_at else None,
                "completed_at": (
                    req.processed_at.isoformat() if req.processed_at else None
                ),
                "failure_reason": req.denial_reason,
            }
        )

    return results
