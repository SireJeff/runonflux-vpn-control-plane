"""
Flux DNS Manager (FDM) Admin API Endpoints

Administrative interface for managing FDM deployments, domains, and sync operations.
These endpoints allow administrators to:
- Create and manage FDM deployments
- Trigger manual sync operations
- View deployment status and sync logs
- Monitor domain health and distribution
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.core.auth import get_current_admin_user
from app.core.database import get_db
from app.models import User
from app.models.fdm import FdmDeployment, FdmDomain, FdmSyncLog
from app.services.fdm.fdm_sync_service import FdmSyncService, get_fdm_sync_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/fdm", tags=["FDM - Flux DNS Manager"])

# Allowed health status values for domain filtering
ALLOWED_HEALTH_STATUSES = {"healthy", "unhealthy", "unknown"}


# =============================================================================
# PYDANTIC SCHEMAS
# =============================================================================


class DeploymentCreate(BaseModel):
    """Request schema for creating a new FDM deployment"""

    flux_app_name: str = Field(
        ...,
        description="Flux application name (e.g., 'fluxvpn-nl-01')",
        min_length=1,
        max_length=255,
    )
    region: Optional[str] = Field(
        None,
        description="Region code (auto-detected from app name if not provided)",
        min_length=2,
        max_length=2,
    )
    domain_pool_size: int = Field(
        default=25,
        description="Number of domains to manage for this deployment",
        ge=1,
        le=1000,
    )
    protocol_name: Optional[str] = Field(
        None,
        description="Protocol name for multi-protocol apps (e.g., 'ssh', 'shadowsocks')",
        max_length=50,
    )
    health_check_port: int = Field(
        default=443,
        description="External port to health-check for this protocol",
        ge=1,
        le=65535,
    )


class DeploymentResponse(BaseModel):
    """Response schema for FDM deployment"""

    id: int
    flux_app_name: str
    region: str
    protocol_name: Optional[str]
    health_check_port: int = 443
    domain_pool_size: int
    base_domain: str
    is_active: bool
    last_sync_at: Optional[datetime]
    last_sync_status: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


class DomainResponse(BaseModel):
    """Response schema for FDM domain"""

    id: int
    deployment_id: int
    domain_name: str
    domain_id: str
    current_ip: Optional[str]
    health_status: str
    assigned_users_count: int
    last_health_check: Optional[datetime]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SyncLogResponse(BaseModel):
    """Response schema for FDM sync log"""

    id: int
    deployment_id: int
    sync_started_at: datetime
    sync_completed_at: Optional[datetime]
    instances_found: int
    instances_healthy: int
    domains_updated: int
    status: str
    errors: Optional[List[Dict[str, Any]]]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RegionInfo(BaseModel):
    """Response schema for region information"""

    code: str
    name: str


class SyncResponse(BaseModel):
    """Response schema for sync operation"""

    success: bool
    message: str
    sync_log: Optional[SyncLogResponse]


# =============================================================================
# DEPLOYMENT MANAGEMENT ENDPOINTS
# =============================================================================


@router.get("/deployments", response_model=List[DeploymentResponse])
async def list_deployments(
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    """
    List all FDM deployments

    Returns a list of all FDM deployments with optional filtering by active status.
    Requires admin authentication.
    """
    query = db.query(FdmDeployment)

    if is_active is not None:
        query = query.filter(FdmDeployment.is_active == is_active)

    deployments = query.order_by(FdmDeployment.created_at.desc()).all()

    logger.info(
        f"Admin {admin.id} listed {len(deployments)} deployments "
        f"(is_active={is_active})"
    )

    return deployments


@router.post(
    "/deployments",
    response_model=DeploymentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_deployment(
    request: DeploymentCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    """
    Create a new FDM deployment

    Creates a new Flux DNS Manager deployment for the specified Flux app.
    The region will be auto-detected from the app name if not provided.

    Requires admin authentication.
    """
    logger.info(f"Admin {admin.id} creating deployment for {request.flux_app_name}")

    try:
        sync_service = get_fdm_sync_service(db)
        deployment = sync_service.create_deployment(
            flux_app_name=request.flux_app_name,
            region=request.region,
            domain_pool_size=request.domain_pool_size,
        )

        return deployment

    except Exception as e:
        logger.error(f"Failed to create deployment for {request.flux_app_name}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create deployment: {str(e)}",
        )


@router.get("/deployments/{deployment_id}", response_model=DeploymentResponse)
async def get_deployment(
    deployment_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    """
    Get a specific FDM deployment

    Returns detailed information about a specific deployment by ID.
    Requires admin authentication.
    """
    deployment = (
        db.query(FdmDeployment).filter(FdmDeployment.id == deployment_id).first()
    )

    if not deployment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Deployment {deployment_id} not found",
        )

    return deployment


@router.post("/deployments/{deployment_id}/sync", response_model=SyncResponse)
async def trigger_deployment_sync(
    deployment_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    """
    Trigger manual sync for a specific deployment

    Manually triggers DNS synchronization for the specified deployment.
    This will discover Flux instances, distribute domains, and update DNS records.

    Requires admin authentication.
    """
    deployment = (
        db.query(FdmDeployment).filter(FdmDeployment.id == deployment_id).first()
    )

    if not deployment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Deployment {deployment_id} not found",
        )

    logger.info(
        f"Admin {admin.id} triggering manual sync for deployment "
        f"{deployment.flux_app_name} (id={deployment_id})"
    )

    try:
        # Directly await the async sync operation
        sync_service = get_fdm_sync_service(db)
        sync_log = await sync_service.sync_deployment(deployment)

        return SyncResponse(
            success=True,
            message=f"Sync completed for {deployment.flux_app_name}",
            sync_log=sync_log,
        )

    except Exception as e:
        logger.error(f"Failed to sync deployment {deployment.flux_app_name}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Sync failed: {str(e)}",
        )


@router.post("/sync-all", response_model=Dict[str, SyncLogResponse])
async def trigger_sync_all(
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    """
    Trigger manual sync for all active deployments

    Manually triggers DNS synchronization for all active FDM deployments.
    Each deployment is synced independently.

    Returns a dictionary mapping flux_app_name to sync results.

    Requires admin authentication.
    """
    logger.info(f"Admin {admin.id} triggering manual sync for all deployments")

    try:
        # Directly await the async sync operation
        sync_service = get_fdm_sync_service(db)
        results = await sync_service.sync_all_deployments()

        # Convert FdmSyncLog objects to response schemas
        response_results = {}
        for app_name, sync_log in results.items():
            response_results[app_name] = sync_log

        return response_results

    except Exception as e:
        logger.error(f"Failed to sync all deployments: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Sync all failed: {str(e)}",
        )


# =============================================================================
# DOMAIN MANAGEMENT ENDPOINTS
# =============================================================================


@router.get("/deployments/{deployment_id}/domains", response_model=List[DomainResponse])
async def list_deployment_domains(
    deployment_id: int,
    health_status: Optional[str] = Query(
        None, description="Filter by health status (healthy, unhealthy, unknown)"
    ),
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    """
    List domains for a specific deployment

    Returns all domain records associated with the specified deployment.
    Optional filtering by health status.

    Requires admin authentication.
    """
    # Validate health_status filter
    if health_status and health_status not in ALLOWED_HEALTH_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid health_status. Must be one of: {', '.join(sorted(ALLOWED_HEALTH_STATUSES))}",
        )

    # Verify deployment exists
    deployment = (
        db.query(FdmDeployment).filter(FdmDeployment.id == deployment_id).first()
    )

    if not deployment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Deployment {deployment_id} not found",
        )

    query = db.query(FdmDomain).filter(FdmDomain.deployment_id == deployment_id)

    if health_status:
        query = query.filter(FdmDomain.health_status == health_status)

    domains = query.order_by(FdmDomain.domain_name).all()

    logger.info(
        f"Admin {admin.id} listed {len(domains)} domains for "
        f"deployment {deployment.flux_app_name} (health_status={health_status})"
    )

    return domains


# =============================================================================
# REGION INFORMATION ENDPOINTS
# =============================================================================


@router.get("/domains/regions", response_model=List[RegionInfo])
async def list_regions(
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    """
    List available regions from active FDM deployments.

    Returns regions that currently have at least one active deployment.
    Derived dynamically from the database, not hardcoded.
    """
    from sqlalchemy import func as sql_func

    from app.core.constants import get_country_name

    regions = (
        db.query(
            sql_func.upper(FdmDeployment.region).label("code"),
        )
        .filter(
            FdmDeployment.is_active == True,
            FdmDeployment.region != "XX",
        )
        .distinct()
        .all()
    )

    logger.info(f"Admin {admin.id} listed {len(regions)} available regions (dynamic)")

    return [RegionInfo(code=r.code, name=get_country_name(r.code)) for r in regions]


# =============================================================================
# SYNC LOG ENDPOINTS
# =============================================================================


@router.get("/sync-logs", response_model=List[SyncLogResponse])
async def list_sync_logs(
    deployment_id: Optional[int] = Query(None, description="Filter by deployment ID"),
    limit: int = Query(
        50, ge=1, le=500, description="Maximum number of logs to return"
    ),
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    """
    List recent sync logs

    Returns recent FDM sync logs with optional filtering by deployment.
    Results are ordered by most recent first.

    Requires admin authentication.
    """
    query = db.query(FdmSyncLog)

    if deployment_id is not None:
        # Verify deployment exists
        deployment = (
            db.query(FdmDeployment).filter(FdmDeployment.id == deployment_id).first()
        )

        if not deployment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Deployment {deployment_id} not found",
            )

        query = query.filter(FdmSyncLog.deployment_id == deployment_id)

    logs = query.order_by(FdmSyncLog.sync_started_at.desc()).limit(limit).all()

    logger.info(
        f"Admin {admin.id} listed {len(logs)} sync logs "
        f"(deployment_id={deployment_id}, limit={limit})"
    )

    return logs
