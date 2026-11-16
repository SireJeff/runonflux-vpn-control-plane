"""
Admin Dashboard Endpoints

Comprehensive admin panel for managing FluxVPN infrastructure:
- Protocol deployments
- Instance management
- User/subscription statistics
- Auto-scaling configuration
"""

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from app.api.v1.endpoints.admin import get_current_admin_user
from app.core.database import get_db
from app.models import (
    Payment,
    Protocol,
    ProtocolInstance,
    Subscription,
    SupportTicket,
    User,
    UserCredential,
)
from app.services.autoscaling.autoscaler import AutoScaler, ScalingRule
from app.services.flux.node_manager import FluxNodeManager, NodeDeploymentError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/dashboard", tags=["Admin Dashboard"])


# =============================================================================
# SCHEMAS
# =============================================================================


class ProtocolStats(BaseModel):
    """Statistics for a single protocol"""

    protocol_id: int
    protocol_name: str
    total_instances: int
    active_instances: int
    inactive_instances: int
    total_users: int
    active_credentials: int
    countries: List[str]
    avg_health_score: float


class InstanceInfo(BaseModel):
    """Detailed instance information"""

    id: int
    flux_app_name: str
    instance_number: int
    ip_address: Optional[str]
    country_code: str
    country_name: str
    city: Optional[str]
    is_active: bool
    current_connections: int
    last_health_check: Optional[datetime]
    created_at: datetime


class SystemStats(BaseModel):
    """Overall system statistics"""

    total_users: int
    active_users: int
    new_users_today: int
    new_users_week: int
    total_subscriptions: int
    active_subscriptions: int
    expiring_soon: int
    total_revenue_usd: Decimal
    revenue_this_month: Decimal
    total_protocols: int
    total_instances: int
    active_instances: int
    open_tickets: int


class DeployProtocolRequest(BaseModel):
    """Request to deploy a protocol"""

    protocol_name: str = Field(
        ...,
        description="Protocol to deploy (shadowsocks, vless, trojan, ssh, outline, http_proxy)",
    )
    instance_count: int = Field(
        default=5, ge=1, le=100, description="Number of instances to deploy"
    )


class ScaleProtocolRequest(BaseModel):
    """Request to scale a protocol"""

    target_count: int = Field(..., ge=0, le=100, description="Target instance count")


class RestartInstanceRequest(BaseModel):
    """Request to restart an instance"""

    instance_id: int


class AutoScaleConfigRequest(BaseModel):
    """Auto-scaling configuration"""

    enabled: bool = True
    min_instances: int = Field(default=5, ge=1)
    max_instances: int = Field(default=50, le=100)
    scale_up_threshold: float = Field(
        default=0.8, description="CPU/connection threshold to scale up"
    )
    scale_down_threshold: float = Field(
        default=0.3, description="Threshold to scale down"
    )
    cooldown_minutes: int = Field(
        default=5, description="Minutes between scaling actions"
    )


# =============================================================================
# SYSTEM OVERVIEW
# =============================================================================


@router.get("/stats", response_model=SystemStats)
async def get_system_stats(
    db: Session = Depends(get_db), admin: User = Depends(get_current_admin_user)
):
    """
    Get comprehensive system statistics

    Returns user counts, subscription stats, revenue, and infrastructure status.
    """
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_ago = now - timedelta(days=7)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # User stats
    total_users = db.query(func.count(User.id)).scalar() or 0
    active_users = (
        db.query(func.count(User.id)).filter(User.is_active == True).scalar() or 0
    )
    new_users_today = (
        db.query(func.count(User.id)).filter(User.created_at >= today_start).scalar()
        or 0
    )
    new_users_week = (
        db.query(func.count(User.id)).filter(User.created_at >= week_ago).scalar() or 0
    )

    # Subscription stats
    total_subscriptions = db.query(func.count(Subscription.id)).scalar() or 0
    active_subscriptions = (
        db.query(func.count(Subscription.id))
        .filter(Subscription.status == "active")
        .scalar()
        or 0
    )
    expiring_soon = (
        db.query(func.count(Subscription.id))
        .filter(
            and_(
                Subscription.status == "active",
                Subscription.expires_at <= now + timedelta(days=7),
            )
        )
        .scalar()
        or 0
    )

    # Revenue stats
    total_revenue = db.query(func.sum(Payment.amount_usd)).filter(
        Payment.status == "completed"
    ).scalar() or Decimal("0")
    revenue_this_month = db.query(func.sum(Payment.amount_usd)).filter(
        and_(Payment.status == "completed", Payment.created_at >= month_start)
    ).scalar() or Decimal("0")

    # Infrastructure stats
    total_protocols = db.query(func.count(Protocol.id)).scalar() or 0
    total_instances = db.query(func.count(ProtocolInstance.id)).scalar() or 0
    active_instances = (
        db.query(func.count(ProtocolInstance.id))
        .filter(ProtocolInstance.is_active == True)
        .scalar()
        or 0
    )

    # Support stats
    open_tickets = (
        db.query(func.count(SupportTicket.id))
        .filter(SupportTicket.status.in_(["open", "in_progress"]))
        .scalar()
        or 0
    )

    return SystemStats(
        total_users=total_users,
        active_users=active_users,
        new_users_today=new_users_today,
        new_users_week=new_users_week,
        total_subscriptions=total_subscriptions,
        active_subscriptions=active_subscriptions,
        expiring_soon=expiring_soon,
        total_revenue_usd=total_revenue,
        revenue_this_month=revenue_this_month,
        total_protocols=total_protocols,
        total_instances=total_instances,
        active_instances=active_instances,
        open_tickets=open_tickets,
    )


# =============================================================================
# PROTOCOL MANAGEMENT
# =============================================================================


@router.get("/protocols", response_model=List[ProtocolStats])
async def get_all_protocols(
    db: Session = Depends(get_db), admin: User = Depends(get_current_admin_user)
):
    """
    Get all protocols with their statistics
    """
    protocols = db.query(Protocol).all()
    result = []

    for protocol in protocols:
        instances = (
            db.query(ProtocolInstance)
            .filter(ProtocolInstance.protocol_id == protocol.id)
            .all()
        )

        active_instances = [i for i in instances if i.is_active]
        countries = list(set(i.country_code for i in instances if i.country_code))

        # Count users with credentials for this protocol
        user_count = (
            db.query(func.count(UserCredential.id))
            .filter(UserCredential.protocol_id == protocol.id)
            .scalar()
            or 0
        )

        active_creds = (
            db.query(func.count(UserCredential.id))
            .filter(
                and_(
                    UserCredential.protocol_id == protocol.id,
                    UserCredential.is_active == True,
                )
            )
            .scalar()
            or 0
        )

        # Calculate average health (placeholder - would come from health checks)
        avg_health = 100.0 if active_instances else 0.0

        result.append(
            ProtocolStats(
                protocol_id=protocol.id,
                protocol_name=protocol.name,
                total_instances=len(instances),
                active_instances=len(active_instances),
                inactive_instances=len(instances) - len(active_instances),
                total_users=user_count,
                active_credentials=active_creds,
                countries=countries,
                avg_health_score=avg_health,
            )
        )

    return result


@router.post("/protocols/deploy")
async def deploy_protocol(
    request: DeployProtocolRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    """
    Deploy a new protocol or add instances to existing protocol
    """
    logger.info(
        f"Admin {admin.email} deploying {request.instance_count} instances of {request.protocol_name}"
    )

    # Check if protocol exists in DB
    protocol = db.query(Protocol).filter(Protocol.name == request.protocol_name).first()

    if not protocol:
        # Create protocol record
        protocol = Protocol(
            name=request.protocol_name,
            display_name=request.protocol_name.replace("_", " ").title(),
            is_active=True,
        )
        db.add(protocol)
        db.commit()
        db.refresh(protocol)

    try:
        node_manager = FluxNodeManager()
        instances = await node_manager.deploy_protocol_instances(
            db=db, protocol=protocol, count=request.instance_count
        )
        await node_manager.close()

        return {
            "success": True,
            "message": f"Deployed {len(instances)} instances of {request.protocol_name}",
            "instances": [
                {
                    "id": i.id,
                    "app_name": i.flux_app_name,
                    "ip": i.ip_address,
                    "country": i.country_code,
                }
                for i in instances
            ],
        }

    except NodeDeploymentError as e:
        logger.error(f"Deployment failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Deployment failed: {str(e)}",
        )


@router.post("/protocols/{protocol_id}/scale")
async def scale_protocol(
    protocol_id: int,
    request: ScaleProtocolRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    """
    Scale protocol instances to target count
    """
    protocol = db.query(Protocol).filter(Protocol.id == protocol_id).first()
    if not protocol:
        raise HTTPException(status_code=404, detail="Protocol not found")

    logger.info(
        f"Admin {admin.email} scaling {protocol.name} to {request.target_count} instances"
    )

    try:
        node_manager = FluxNodeManager()
        added, removed = await node_manager.scale_protocol(
            db=db, protocol=protocol, target_count=request.target_count
        )
        await node_manager.close()

        return {
            "success": True,
            "protocol": protocol.name,
            "added_count": len(added),
            "removed_count": len(removed),
            "current_count": request.target_count,
        }

    except NodeDeploymentError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Scaling failed: {str(e)}",
        )


# =============================================================================
# INSTANCE MANAGEMENT
# =============================================================================


@router.get("/instances", response_model=List[InstanceInfo])
async def get_all_instances(
    protocol_id: Optional[int] = Query(None, description="Filter by protocol"),
    country: Optional[str] = Query(None, description="Filter by country code"),
    active_only: bool = Query(False, description="Only show active instances"),
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    """
    Get all protocol instances with optional filters
    """
    query = db.query(ProtocolInstance)

    if protocol_id:
        query = query.filter(ProtocolInstance.protocol_id == protocol_id)
    if country:
        query = query.filter(ProtocolInstance.country_code == country.upper())
    if active_only:
        query = query.filter(ProtocolInstance.is_active == True)

    instances = query.order_by(ProtocolInstance.created_at.desc()).all()

    return [
        InstanceInfo(
            id=i.id,
            flux_app_name=i.flux_app_name,
            instance_number=i.instance_number,
            ip_address=i.ip_address,
            country_code=i.country_code,
            country_name=i.country_name,
            city=i.city,
            is_active=i.is_active,
            current_connections=i.current_connections or 0,
            last_health_check=i.last_health_check,
            created_at=i.created_at,
        )
        for i in instances
    ]


@router.post("/instances/{instance_id}/restart")
async def restart_instance(
    instance_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    """
    Restart a specific instance
    """
    instance = (
        db.query(ProtocolInstance).filter(ProtocolInstance.id == instance_id).first()
    )
    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")

    logger.info(f"Admin {admin.email} restarting instance {instance.flux_app_name}")

    try:
        node_manager = FluxNodeManager()
        success = await node_manager.restart_instance(instance)
        await node_manager.close()

        return {
            "success": success,
            "message": f"Instance {instance.flux_app_name} {'restarted' if success else 'failed to restart'}",
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Restart failed: {str(e)}",
        )


@router.delete("/instances/{instance_id}")
async def remove_instance(
    instance_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    """
    Remove a specific instance
    """
    instance = (
        db.query(ProtocolInstance).filter(ProtocolInstance.id == instance_id).first()
    )
    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")

    logger.info(f"Admin {admin.email} removing instance {instance.flux_app_name}")

    try:
        node_manager = FluxNodeManager()
        success = await node_manager.remove_instance(db, instance)
        await node_manager.close()

        return {
            "success": success,
            "message": f"Instance {instance.flux_app_name} {'removed' if success else 'failed to remove'}",
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Remove failed: {str(e)}",
        )


@router.get("/instances/{instance_id}/logs")
async def get_instance_logs(
    instance_id: int,
    lines: int = Query(100, ge=10, le=1000),
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    """
    Get logs from a specific instance
    """
    instance = (
        db.query(ProtocolInstance).filter(ProtocolInstance.id == instance_id).first()
    )
    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")

    try:
        node_manager = FluxNodeManager()
        logs = await node_manager.get_instance_logs(instance, lines=lines)
        await node_manager.close()

        return {"instance": instance.flux_app_name, "lines": lines, "logs": logs}

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get logs: {str(e)}",
        )


# =============================================================================
# AUTO-SCALING CONFIGURATION
# =============================================================================


@router.get("/autoscaling/config")
async def get_autoscaling_config(admin: User = Depends(get_current_admin_user)):
    """
    Get current auto-scaling configuration
    """
    autoscaler = AutoScaler()
    config = autoscaler.get_config()

    return {
        "enabled": config.get("enabled", False),
        "rules": config.get("rules", {}),
        "last_scaling_action": config.get("last_action"),
        "next_check": config.get("next_check"),
    }


@router.put("/autoscaling/config")
async def update_autoscaling_config(
    request: AutoScaleConfigRequest, admin: User = Depends(get_current_admin_user)
):
    """
    Update auto-scaling configuration
    """
    logger.info(
        f"Admin {admin.email} updating autoscaling config: enabled={request.enabled}"
    )

    autoscaler = AutoScaler()
    autoscaler.update_config(
        enabled=request.enabled,
        min_instances=request.min_instances,
        max_instances=request.max_instances,
        scale_up_threshold=request.scale_up_threshold,
        scale_down_threshold=request.scale_down_threshold,
        cooldown_minutes=request.cooldown_minutes,
    )

    return {
        "success": True,
        "message": "Auto-scaling configuration updated",
        "config": {
            "enabled": request.enabled,
            "min_instances": request.min_instances,
            "max_instances": request.max_instances,
            "scale_up_threshold": request.scale_up_threshold,
            "scale_down_threshold": request.scale_down_threshold,
            "cooldown_minutes": request.cooldown_minutes,
        },
    }


@router.post("/autoscaling/trigger")
async def trigger_autoscaling(
    db: Session = Depends(get_db), admin: User = Depends(get_current_admin_user)
):
    """
    Manually trigger an auto-scaling check
    """
    logger.info(f"Admin {admin.email} manually triggering autoscaling check")

    autoscaler = AutoScaler()
    result = await autoscaler.check_and_scale(db)

    return {
        "success": True,
        "actions_taken": result.get("actions", []),
        "protocols_checked": result.get("protocols_checked", 0),
        "scaling_decisions": result.get("decisions", {}),
    }


# =============================================================================
# USER MANAGEMENT (Quick Actions)
# =============================================================================


@router.get("/users/recent")
async def get_recent_users(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    """
    Get recently registered users
    """
    users = db.query(User).order_by(User.created_at.desc()).limit(limit).all()

    return [
        {
            "id": u.id,
            "email": u.email,
            "telegram_id": u.telegram_id,
            "is_active": u.is_active,
            "created_at": u.created_at,
            "subscription_status": u.subscription.status if u.subscription else None,
        }
        for u in users
    ]


@router.get("/subscriptions/expiring")
async def get_expiring_subscriptions(
    days: int = Query(7, ge=1, le=30),
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    """
    Get subscriptions expiring within specified days
    """
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=days)

    subscriptions = (
        db.query(Subscription)
        .filter(
            and_(Subscription.status == "active", Subscription.expires_at <= cutoff)
        )
        .order_by(Subscription.expires_at.asc())
        .all()
    )

    return [
        {
            "id": s.id,
            "user_id": s.user_id,
            "user_email": s.user.email if s.user else None,
            "plan_name": s.plan.name if s.plan else None,
            "end_date": s.end_date,
            "days_remaining": (
                (s.end_date - datetime.now(timezone.utc).replace(tzinfo=None)).days
                if s.end_date
                else 0
            ),
        }
        for s in subscriptions
    ]
