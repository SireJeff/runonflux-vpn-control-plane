"""
Support Pydantic schemas for tickets and messages
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

# ============================================================================
# SUPPORT TICKET SCHEMAS
# ============================================================================


class SupportTicketBase(BaseModel):
    """Base support ticket schema"""

    subject: str = Field(..., max_length=500, min_length=5)
    priority: str = Field(default="medium", pattern="^(low|medium|high|urgent)$")


class SupportTicketCreate(SupportTicketBase):
    """Schema for support ticket creation"""

    user_id: int
    initial_message: str = Field(
        ..., min_length=10, description="First message in the ticket"
    )


class SupportTicketUpdate(BaseModel):
    """Schema for support ticket updates"""

    status: Optional[str] = Field(None, pattern="^(open|pending|resolved|closed)$")
    priority: Optional[str] = Field(None, pattern="^(low|medium|high|urgent)$")
    assigned_to: Optional[int] = None


class SupportTicketResponse(SupportTicketBase):
    """Schema for support ticket in responses"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    status: str
    assigned_to: Optional[int] = None
    telegram_message_id: Optional[int] = None
    created_at: datetime
    resolved_at: Optional[datetime] = None


class SupportTicketWithMessages(SupportTicketResponse):
    """Support ticket with messages"""

    messages: list["SupportMessageResponse"]
    unread_count: int = Field(..., description="Number of unread messages")


# ============================================================================
# SUPPORT MESSAGE SCHEMAS
# ============================================================================


class SupportMessageBase(BaseModel):
    """Base support message schema"""

    message: str = Field(..., min_length=1)


class SupportMessageCreate(SupportMessageBase):
    """Schema for support message creation"""

    ticket_id: int
    sender_id: int
    is_admin: bool = False


class SupportMessageResponse(SupportMessageBase):
    """Schema for support message in responses"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    ticket_id: int
    sender_id: int
    is_admin: bool
    telegram_message_id: Optional[int] = None
    read_at: Optional[datetime] = None
    created_at: datetime


class TicketCreateRequest(BaseModel):
    """Request to create a support ticket"""

    subject: str = Field(..., max_length=500, min_length=5)
    message: str = Field(..., min_length=10)
    priority: str = Field(default="medium", pattern="^(low|medium|high|urgent)$")


class TicketCreateResponse(BaseModel):
    """Response for ticket creation"""

    ticket_id: int
    status: str
    message: str = (
        "Your support ticket has been created. Our team will respond shortly."
    )


class MessageSendRequest(BaseModel):
    """Request to send a message in a ticket"""

    ticket_id: int
    message: str = Field(..., min_length=1)


class MessageSendResponse(BaseModel):
    """Response for message send"""

    message_id: int
    ticket_id: int
    status: str
    message: str
