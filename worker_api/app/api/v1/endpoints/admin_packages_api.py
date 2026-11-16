"""Reseller-facing API: subscription package CRUD."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth.role_dependencies import RoleChecker
from app.core.database import get_db
from app.models.admin_packages import AdminPackage
from app.schemas.admin_packages import (
    PackageCreateRequest,
    PackageResponse,
    PackageUpdateRequest,
)
from app.services.subscriptions.package_seeder import seed_default_packages

router = APIRouter(prefix="/admin/packages", tags=["Admin Packages"])


@router.get("", response_model=list[PackageResponse])
def list_packages(
    include_inactive: bool = False,
    current: dict = Depends(RoleChecker(["admin", "super_admin"])),
    db: Session = Depends(get_db),
):
    """List reseller's packages. Default excludes archived (is_active=False)."""
    q = db.query(AdminPackage).filter(AdminPackage.admin_id == current["id"])
    if not include_inactive:
        q = q.filter(AdminPackage.is_active == True)  # noqa: E712
    return q.order_by(AdminPackage.display_order, AdminPackage.id).all()


@router.post("", response_model=PackageResponse, status_code=status.HTTP_201_CREATED)
def create_package(
    req: PackageCreateRequest,
    current: dict = Depends(RoleChecker(["admin"])),
    db: Session = Depends(get_db),
):
    pkg = AdminPackage(admin_id=current["id"], **req.model_dump())
    db.add(pkg)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409, detail="Package name already exists for this admin"
        )
    db.refresh(pkg)
    return pkg


@router.post("/seed-defaults")
def seed_defaults(
    current: dict = Depends(RoleChecker(["admin"])),
    db: Session = Depends(get_db),
):
    """Load the default starter catalog. Idempotent (no-op if any packages exist)."""
    inserted = seed_default_packages(db, current["id"])
    db.commit()
    return {"inserted": inserted}


@router.put("/{package_id}", response_model=PackageResponse)
def update_package(
    package_id: int,
    req: PackageUpdateRequest,
    current: dict = Depends(RoleChecker(["admin"])),
    db: Session = Depends(get_db),
):
    pkg = (
        db.query(AdminPackage)
        .filter(
            AdminPackage.id == package_id,
            AdminPackage.admin_id == current["id"],
        )
        .first()
    )
    if not pkg:
        raise HTTPException(status_code=404, detail="Package not found")

    for field, value in req.model_dump(exclude_unset=True).items():
        setattr(pkg, field, value)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Name conflict")
    db.refresh(pkg)
    return pkg


@router.delete("/{package_id}", status_code=status.HTTP_204_NO_CONTENT)
def archive_package(
    package_id: int,
    current: dict = Depends(RoleChecker(["admin"])),
    db: Session = Depends(get_db),
):
    """Soft-delete via is_active=False (preserves order history linkage)."""
    pkg = (
        db.query(AdminPackage)
        .filter(
            AdminPackage.id == package_id,
            AdminPackage.admin_id == current["id"],
        )
        .first()
    )
    if not pkg:
        raise HTTPException(status_code=404, detail="Package not found")
    pkg.is_active = False
    db.commit()
    return None
