"""Reseller-facing order management + receipt retrieval.

GET + POST endpoints for order lifecycle (create, approve, reject).
"""

import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.auth.role_dependencies import RoleChecker
from app.core.crypto import decrypt_token
from app.core.database import get_db
from app.models.admin_bots import AdminBot
from app.models.admin_users import AdminUser
from app.models.user_orders import UserOrder
from app.schemas.user_orders import OrderCreateRequest, OrderResponse
from app.services.orders.order_service import OrderError, OrderService
from app.services.orders.receipt_storage import download_and_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/orders", tags=["Admin Orders"])


@router.get("", response_model=list[OrderResponse])
def list_orders(
    status_filter: Optional[str] = Query(None, alias="status"),
    current: dict = Depends(RoleChecker(["admin", "super_admin"])),
    db: Session = Depends(get_db),
):
    """List the reseller's orders, newest first. Optional status filter."""
    q = db.query(UserOrder).filter(UserOrder.admin_id == current["id"])
    if status_filter:
        q = q.filter(UserOrder.status == status_filter)
    return q.order_by(UserOrder.created_at.desc()).limit(200).all()


@router.get("/{order_id}", response_model=OrderResponse)
def get_order(
    order_id: int,
    current: dict = Depends(RoleChecker(["admin", "super_admin"])),
    db: Session = Depends(get_db),
):
    order = (
        db.query(UserOrder)
        .filter(
            UserOrder.id == order_id,
            UserOrder.admin_id == current["id"],
        )
        .first()
    )
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


@router.get("/{order_id}/receipt")
def get_receipt(
    order_id: int,
    current: dict = Depends(RoleChecker(["admin", "super_admin"])),
    db: Session = Depends(get_db),
):
    """Serve the stored receipt image. Admin-only -- never public."""
    order = (
        db.query(UserOrder)
        .filter(
            UserOrder.id == order_id,
            UserOrder.admin_id == current["id"],
        )
        .first()
    )
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if not order.receipt_local_path:
        raise HTTPException(status_code=404, detail="Receipt not available")

    if not os.path.exists(order.receipt_local_path):
        raise HTTPException(status_code=410, detail="Receipt file missing")

    return FileResponse(order.receipt_local_path, media_type="image/jpeg")


# ---------------------------------------------------------------------------
# POST endpoints (Task 9D)
# ---------------------------------------------------------------------------


@router.post("", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
def create_order_endpoint(
    req: OrderCreateRequest,
    current: dict = Depends(RoleChecker(["end_user"])),
    db: Session = Depends(get_db),
):
    """End-user creates a new order with receipt attached."""
    user = db.query(AdminUser).filter(AdminUser.id == current["id"]).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    try:
        order = OrderService(db).create_order(
            user=user,
            package_id=req.package_id,
            macro_region=req.macro_region,
            wallet_credit_to_apply_tomans=req.wallet_credit_to_apply_tomans,
            receipt_file_id=req.receipt_file_id,
            receipt_file_unique_id=req.receipt_file_unique_id,
        )
    except OrderError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return order


@router.post("/{order_id}/approve", response_model=OrderResponse)
def approve_order_endpoint(
    order_id: int,
    current: dict = Depends(RoleChecker(["admin"])),
    db: Session = Depends(get_db),
):
    """Admin approves a pending order. Activates user + delivers credentials."""
    try:
        return OrderService(db).approve_order(order_id, current["id"])
    except OrderError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{order_id}/reject", response_model=OrderResponse)
def reject_order_endpoint(
    order_id: int,
    payload: Optional[dict] = None,
    current: dict = Depends(RoleChecker(["admin"])),
    db: Session = Depends(get_db),
):
    """Admin rejects a pending order. Refunds wallet credit, notifies user."""
    reason = (payload or {}).get("reason")
    try:
        return OrderService(db).reject_order(order_id, current["id"], reason)
    except OrderError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{order_id}/retry-receipt", response_model=OrderResponse)
async def retry_receipt_download(
    order_id: int,
    current: dict = Depends(RoleChecker(["admin", "super_admin"])),
    db: Session = Depends(get_db),
):
    """Re-attempt the receipt download when admin hits 404 on View Receipt."""
    order = (
        db.query(UserOrder)
        .filter(
            UserOrder.id == order_id,
            UserOrder.admin_id == current["id"],
        )
        .first()
    )
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if not order.receipt_file_id:
        raise HTTPException(
            status_code=400, detail="Order has no receipt file_id on record"
        )

    bot = db.query(AdminBot).filter(AdminBot.admin_id == current["id"]).first()
    if not bot:
        raise HTTPException(status_code=400, detail="No bot registered for this admin")

    token = decrypt_token(bot.bot_token_enc)
    try:
        path = await download_and_store(token, order.receipt_file_id, order.id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Telegram download failed: {e}")

    order.receipt_local_path = path
    db.commit()
    db.refresh(order)
    return order
