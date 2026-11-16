"""
Support Ticket System endpoints
"""

import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any, List, Optional, cast

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import and_, desc, or_
from sqlalchemy.orm import Session

from app.core.auth import get_current_admin_user, get_current_user
from app.core.database import get_db
from app.models import SupportTicket, TicketMessage, User
from app.schemas import SuccessResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/support", tags=["Support"])


# ============================================================================
# ENUMS
# ============================================================================


class TicketPriority(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    urgent = "urgent"


class TicketCategory(str, Enum):
    technical = "technical"
    billing = "billing"
    account = "account"
    feature_request = "feature_request"
    other = "other"


class TicketStatus(str, Enum):
    open = "open"
    in_progress = "in_progress"
    waiting_customer = "waiting_customer"
    resolved = "resolved"
    closed = "closed"


# ============================================================================
# REQUEST/RESPONSE SCHEMAS
# ============================================================================


class TicketCreate(BaseModel):
    """Create new support ticket"""

    subject: str = Field(
        ..., min_length=5, max_length=200, description="Ticket subject"
    )
    description: str = Field(
        ..., min_length=10, max_length=5000, description="Detailed description"
    )
    category: TicketCategory = Field(
        default=TicketCategory.other, description="Ticket category"
    )
    priority: TicketPriority = Field(
        default=TicketPriority.medium, description="Priority level"
    )


class TicketUpdate(BaseModel):
    """Update ticket details"""

    subject: Optional[str] = Field(None, min_length=5, max_length=200)
    priority: Optional[TicketPriority] = None
    category: Optional[TicketCategory] = None


class TicketMessageCreate(BaseModel):
    """Add message to ticket"""

    message: str = Field(
        ..., min_length=1, max_length=5000, description="Message content"
    )
    is_internal: bool = Field(default=False, description="Internal note (admin only)")


class TicketMessageResponse(BaseModel):
    """Ticket message response"""

    id: int
    ticket_id: int
    user_id: int
    user_name: Optional[str]
    is_staff: bool
    is_internal: bool
    message: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TicketResponse(BaseModel):
    """Support ticket response"""

    id: int
    user_id: int
    ticket_number: str
    subject: str
    description: str
    category: str
    priority: str
    status: str
    created_at: datetime
    updated_at: datetime
    resolved_at: Optional[datetime]
    assigned_to: Optional[int]
    assigned_to_name: Optional[str]
    message_count: int
    last_message_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


class TicketDetailResponse(BaseModel):
    """Detailed ticket response with messages"""

    ticket: TicketResponse
    messages: List[TicketMessageResponse]


class TicketStats(BaseModel):
    """Ticket statistics"""

    total_tickets: int
    open_tickets: int
    in_progress_tickets: int
    resolved_tickets: int
    closed_tickets: int
    avg_resolution_time_hours: Optional[float]


# ============================================================================
# USER TICKET ENDPOINTS
# ============================================================================


@router.post(
    "/tickets", response_model=TicketResponse, status_code=status.HTTP_201_CREATED
)
async def create_ticket(
    ticket_data: TicketCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Create a new support ticket

    **Categories:**
    - technical: Technical issues (connection, performance, etc.)
    - billing: Payment and subscription issues
    - account: Account management issues
    - feature_request: Suggestions and feature requests
    - other: General inquiries

    **Priority Levels:**
    - low: General questions, minor issues
    - medium: Standard issues (default)
    - high: Service disruption, important matters
    - urgent: Critical issues affecting service
    """
    logger.info(
        f"User {current_user.id} creating support ticket: {ticket_data.subject}"
    )

    # Generate ticket number (format: YYYYMMDD-XXXXX)
    from random import randint

    ticket_number = f"{datetime.now(timezone.utc).replace(tzinfo=None).strftime('%Y%m%d')}-{randint(10000, 99999)}"

    # Ensure ticket number is unique
    while db.query(SupportTicket).filter_by(ticket_number=ticket_number).first():
        ticket_number = f"{datetime.now(timezone.utc).replace(tzinfo=None).strftime('%Y%m%d')}-{randint(10000, 99999)}"

    # Create ticket
    ticket = SupportTicket(
        user_id=current_user.id,
        ticket_number=ticket_number,
        subject=ticket_data.subject,
        description=ticket_data.description,
        category=ticket_data.category.value,
        priority=ticket_data.priority.value,
        status="open",
    )

    db.add(ticket)
    db.commit()
    db.refresh(ticket)

    # Create initial message with description
    initial_message = TicketMessage(
        ticket_id=ticket.id,
        user_id=current_user.id,
        message=ticket_data.description,
        is_staff=False,
        is_internal=False,
    )

    db.add(initial_message)
    db.commit()

    logger.info(f"Ticket {ticket.ticket_number} created successfully")

    return TicketResponse(
        id=ticket.id,
        user_id=ticket.user_id,
        ticket_number=ticket.ticket_number,
        subject=ticket.subject,
        description=ticket.description,
        category=ticket.category,
        priority=ticket.priority,
        status=ticket.status,
        created_at=ticket.created_at,
        updated_at=ticket.updated_at,
        resolved_at=ticket.resolved_at,
        assigned_to=ticket.assigned_to,
        assigned_to_name=None,
        message_count=1,
        last_message_at=initial_message.created_at,
    )


@router.get("/tickets", response_model=List[TicketResponse])
async def list_user_tickets(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    status_filter: Optional[TicketStatus] = None,
    category_filter: Optional[TicketCategory] = None,
    limit: int = Query(default=50, le=100),
    offset: int = Query(default=0, ge=0),
):
    """
    List current user's support tickets

    Filter by status and category.
    Returns tickets ordered by most recent first.
    """
    query = db.query(SupportTicket).filter_by(user_id=current_user.id)

    if status_filter:
        query = query.filter(SupportTicket.status == status_filter.value)

    if category_filter:
        query = query.filter(SupportTicket.category == category_filter.value)

    tickets = (
        query.order_by(desc(SupportTicket.created_at)).offset(offset).limit(limit).all()
    )

    result = []
    for ticket in tickets:
        # Count messages
        message_count = (
            db.query(TicketMessage)
            .filter_by(
                ticket_id=ticket.id, is_internal=False  # Don't count internal notes
            )
            .count()
        )

        # Get last message
        last_message = (
            db.query(TicketMessage)
            .filter_by(ticket_id=ticket.id, is_internal=False)
            .order_by(desc(TicketMessage.created_at))
            .first()
        )

        # Get assigned admin name
        assigned_name = None
        if ticket.assigned_to:
            assigned_admin = db.query(User).filter_by(id=ticket.assigned_to).first()
            assigned_name = assigned_admin.telegram_username if assigned_admin else None

        result.append(
            TicketResponse(
                id=ticket.id,
                user_id=ticket.user_id,
                ticket_number=ticket.ticket_number,
                subject=ticket.subject,
                description=ticket.description,
                category=ticket.category,
                priority=ticket.priority,
                status=ticket.status,
                created_at=ticket.created_at,
                updated_at=ticket.updated_at,
                resolved_at=ticket.resolved_at,
                assigned_to=ticket.assigned_to,
                assigned_to_name=assigned_name,
                message_count=message_count,
                last_message_at=(
                    last_message.created_at if last_message else ticket.created_at
                ),
            )
        )

    return result


@router.get("/tickets/{ticket_id}", response_model=TicketDetailResponse)
async def get_ticket(
    ticket_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get detailed ticket information with all messages

    Returns ticket details and message history.
    Internal notes are only visible to staff.
    """
    ticket = (
        db.query(SupportTicket).filter_by(id=ticket_id, user_id=current_user.id).first()
    )

    if not ticket:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found"
        )

    # Get messages (exclude internal notes for non-staff)
    messages_query = db.query(TicketMessage).filter_by(ticket_id=ticket.id)

    if not current_user.is_admin:
        messages_query = messages_query.filter(TicketMessage.is_internal == False)

    messages = messages_query.order_by(TicketMessage.created_at.asc()).all()

    # Build message responses
    message_responses = []
    for msg in messages:
        user = db.query(User).filter_by(id=msg.user_id).first()
        message_responses.append(
            TicketMessageResponse(
                id=msg.id,
                ticket_id=msg.ticket_id,
                user_id=msg.user_id,
                user_name=user.telegram_username if user else "Unknown",
                is_staff=msg.is_staff,
                is_internal=msg.is_internal,
                message=msg.message,
                created_at=msg.created_at,
            )
        )

    # Get assigned admin name
    assigned_name = None
    if ticket.assigned_to:
        assigned_admin = db.query(User).filter_by(id=ticket.assigned_to).first()
        assigned_name = assigned_admin.telegram_username if assigned_admin else None

    ticket_response = TicketResponse(
        id=ticket.id,
        user_id=ticket.user_id,
        ticket_number=ticket.ticket_number,
        subject=ticket.subject,
        description=ticket.description,
        category=ticket.category,
        priority=ticket.priority,
        status=ticket.status,
        created_at=ticket.created_at,
        updated_at=ticket.updated_at,
        resolved_at=ticket.resolved_at,
        assigned_to=ticket.assigned_to,
        assigned_to_name=assigned_name,
        message_count=len(message_responses),
        last_message_at=messages[-1].created_at if messages else ticket.created_at,
    )

    return TicketDetailResponse(ticket=ticket_response, messages=message_responses)


@router.post(
    "/tickets/{ticket_id}/messages",
    response_model=TicketMessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_ticket_message(
    ticket_id: int,
    message_data: TicketMessageCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Add a message to a ticket

    Users can add messages to their own tickets.
    Admins can add messages and internal notes to any ticket.
    """
    # Check if ticket exists and user has access
    ticket = db.query(SupportTicket).filter_by(id=ticket_id).first()

    if not ticket:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found"
        )

    # Non-admin users can only message their own tickets
    if not current_user.is_admin and ticket.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only add messages to your own tickets",
        )

    # Non-admin users cannot create internal notes
    if not current_user.is_admin and message_data.is_internal:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only staff can create internal notes",
        )

    # Check if ticket is closed
    if ticket.status == "closed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot add messages to closed tickets",
        )

    # Create message
    message = TicketMessage(
        ticket_id=ticket_id,
        user_id=current_user.id,
        message=message_data.message,
        is_staff=current_user.is_admin,
        is_internal=message_data.is_internal,
    )

    db.add(message)

    # Update ticket status
    ticket_obj = cast(Any, ticket)
    if current_user.is_admin:
        # Admin replied, set to in_progress
        if ticket.status == "open":
            ticket_obj.status = "in_progress"
    else:
        # User replied, set to waiting_customer if it was in_progress
        if ticket.status == "in_progress":
            ticket_obj.status = "open"

    ticket_obj.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)

    db.commit()
    db.refresh(message)

    logger.info(f"Message added to ticket {ticket_id} by user {current_user.id}")

    return TicketMessageResponse(
        id=message.id,
        ticket_id=message.ticket_id,
        user_id=message.user_id,
        user_name=current_user.telegram_username,
        is_staff=message.is_staff,
        is_internal=message.is_internal,
        message=message.message,
        created_at=message.created_at,
    )


@router.put("/tickets/{ticket_id}", response_model=TicketResponse)
async def update_ticket(
    ticket_id: int,
    ticket_update: TicketUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Update ticket details

    Users can update their own tickets (subject, priority, category).
    Only tickets with status 'open' can be updated by users.
    """
    ticket = (
        db.query(SupportTicket).filter_by(id=ticket_id, user_id=current_user.id).first()
    )

    if not ticket:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found"
        )

    if ticket.status not in ["open", "waiting_customer"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only update tickets with 'open' or 'waiting_customer' status",
        )

    # Update fields
    update_data = ticket_update.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        if field in ["priority", "category"] and value:
            setattr(ticket, field, value.value if hasattr(value, "value") else value)
        elif value is not None:
            setattr(ticket, field, value)

    ticket_obj = cast(Any, ticket)
    ticket_obj.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)

    db.commit()
    db.refresh(ticket)

    logger.info(f"Ticket {ticket_id} updated by user {current_user.id}")

    # Get message count
    message_count = (
        db.query(TicketMessage)
        .filter_by(ticket_id=ticket.id, is_internal=False)
        .count()
    )

    # Get last message
    last_message = (
        db.query(TicketMessage)
        .filter_by(ticket_id=ticket.id, is_internal=False)
        .order_by(desc(TicketMessage.created_at))
        .first()
    )

    return TicketResponse(
        id=ticket.id,
        user_id=ticket.user_id,
        ticket_number=ticket.ticket_number,
        subject=ticket.subject,
        description=ticket.description,
        category=ticket.category,
        priority=ticket.priority,
        status=ticket.status,
        created_at=ticket.created_at,
        updated_at=ticket.updated_at,
        resolved_at=ticket.resolved_at,
        assigned_to=ticket.assigned_to,
        assigned_to_name=None,
        message_count=message_count,
        last_message_at=last_message.created_at if last_message else ticket.created_at,
    )


@router.post("/tickets/{ticket_id}/close", response_model=SuccessResponse)
async def close_ticket(
    ticket_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Close a ticket

    Users can close their own resolved tickets.
    """
    ticket = (
        db.query(SupportTicket).filter_by(id=ticket_id, user_id=current_user.id).first()
    )

    if not ticket:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found"
        )

    if ticket.status == "closed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Ticket is already closed"
        )

    ticket_obj = cast(Any, ticket)
    ticket_obj.status = "closed"
    ticket_obj.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)

    if not ticket.resolved_at:
        ticket_obj.resolved_at = datetime.now(timezone.utc).replace(tzinfo=None)

    db.commit()

    logger.info(f"Ticket {ticket_id} closed by user {current_user.id}")

    return SuccessResponse(
        message="Ticket closed successfully",
        data={"ticket_id": ticket_id, "ticket_number": ticket.ticket_number},
    )


# ============================================================================
# ADMIN TICKET ENDPOINTS
# ============================================================================


@router.get("/admin/tickets", response_model=List[TicketResponse])
async def list_all_tickets(
    admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
    status_filter: Optional[TicketStatus] = None,
    category_filter: Optional[TicketCategory] = None,
    priority_filter: Optional[TicketPriority] = None,
    assigned_filter: Optional[bool] = None,
    search: Optional[str] = None,
    limit: int = Query(default=50, le=100),
    offset: int = Query(default=0, ge=0),
):
    """
    List all support tickets (Admin only)

    **Filters:**
    - status: Filter by ticket status
    - category: Filter by category
    - priority: Filter by priority level
    - assigned: Show only assigned (true) or unassigned (false) tickets
    - search: Search in ticket number, subject, or user info
    """
    query = db.query(SupportTicket)

    if status_filter:
        query = query.filter(SupportTicket.status == status_filter.value)

    if category_filter:
        query = query.filter(SupportTicket.category == category_filter.value)

    if priority_filter:
        query = query.filter(SupportTicket.priority == priority_filter.value)

    if assigned_filter is not None:
        if assigned_filter:
            query = query.filter(SupportTicket.assigned_to.isnot(None))
        else:
            query = query.filter(SupportTicket.assigned_to.is_(None))

    if search:
        search_filter = f"%{search}%"
        query = query.filter(
            or_(
                SupportTicket.ticket_number.ilike(search_filter),
                SupportTicket.subject.ilike(search_filter),
            )
        )

    tickets = (
        query.order_by(desc(SupportTicket.created_at)).offset(offset).limit(limit).all()
    )

    result = []
    for ticket in tickets:
        message_count = db.query(TicketMessage).filter_by(ticket_id=ticket.id).count()
        last_message = (
            db.query(TicketMessage)
            .filter_by(ticket_id=ticket.id)
            .order_by(desc(TicketMessage.created_at))
            .first()
        )

        assigned_name = None
        if ticket.assigned_to:
            assigned_admin = db.query(User).filter_by(id=ticket.assigned_to).first()
            assigned_name = assigned_admin.telegram_username if assigned_admin else None

        result.append(
            TicketResponse(
                id=ticket.id,
                user_id=ticket.user_id,
                ticket_number=ticket.ticket_number,
                subject=ticket.subject,
                description=ticket.description,
                category=ticket.category,
                priority=ticket.priority,
                status=ticket.status,
                created_at=ticket.created_at,
                updated_at=ticket.updated_at,
                resolved_at=ticket.resolved_at,
                assigned_to=ticket.assigned_to,
                assigned_to_name=assigned_name,
                message_count=message_count,
                last_message_at=(
                    last_message.created_at if last_message else ticket.created_at
                ),
            )
        )

    return result


@router.post("/admin/tickets/{ticket_id}/assign", response_model=SuccessResponse)
async def assign_ticket(
    ticket_id: int,
    admin_id: Optional[int] = None,
    admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """
    Assign ticket to admin (Admin only)

    If admin_id is not provided, assigns to current admin.
    """
    ticket = db.query(SupportTicket).filter_by(id=ticket_id).first()

    if not ticket:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found"
        )

    assign_to = admin_id if admin_id else admin.id

    # Verify admin exists
    target_admin = db.query(User).filter_by(id=assign_to, is_admin=True).first()

    if not target_admin:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Admin user not found"
        )

    ticket_obj = cast(Any, ticket)
    ticket_obj.assigned_to = assign_to
    ticket_obj.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)

    if ticket.status == "open":
        ticket_obj.status = "in_progress"

    db.commit()

    logger.info(f"Ticket {ticket_id} assigned to admin {assign_to} by {admin.id}")

    return SuccessResponse(
        message=f"Ticket assigned to {target_admin.telegram_username}",
        data={"ticket_id": ticket_id, "assigned_to": assign_to},
    )


@router.post("/admin/tickets/{ticket_id}/resolve", response_model=SuccessResponse)
async def resolve_ticket(
    ticket_id: int,
    admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """
    Mark ticket as resolved (Admin only)
    """
    ticket = db.query(SupportTicket).filter_by(id=ticket_id).first()

    if not ticket:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found"
        )

    ticket_obj = cast(Any, ticket)
    ticket_obj.status = "resolved"
    ticket_obj.resolved_at = datetime.now(timezone.utc).replace(tzinfo=None)
    ticket_obj.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)

    db.commit()

    logger.info(f"Ticket {ticket_id} marked as resolved by admin {admin.id}")

    return SuccessResponse(
        message="Ticket marked as resolved", data={"ticket_id": ticket_id}
    )


@router.get("/admin/stats", response_model=TicketStats)
async def get_ticket_stats(
    admin: User = Depends(get_current_admin_user), db: Session = Depends(get_db)
):
    """
    Get ticket statistics (Admin only)
    """
    total = db.query(SupportTicket).count()
    open_count = db.query(SupportTicket).filter_by(status="open").count()
    in_progress = db.query(SupportTicket).filter_by(status="in_progress").count()
    resolved = db.query(SupportTicket).filter_by(status="resolved").count()
    closed = db.query(SupportTicket).filter_by(status="closed").count()

    # Calculate average resolution time
    resolved_tickets = (
        db.query(SupportTicket).filter(SupportTicket.resolved_at.isnot(None)).all()
    )

    avg_resolution = None
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
        avg_resolution = total_hours / len(resolved_tickets)

    return TicketStats(
        total_tickets=total,
        open_tickets=open_count,
        in_progress_tickets=in_progress,
        resolved_tickets=resolved,
        closed_tickets=closed,
        avg_resolution_time_hours=avg_resolution,
    )
