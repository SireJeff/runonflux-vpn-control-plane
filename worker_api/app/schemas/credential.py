"""
Credential Pydantic schemas for user credentials and protocol assignments
"""

from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field

# ============================================================================
# USER CREDENTIAL SCHEMAS
# ============================================================================


class UserCredentialBase(BaseModel):
    """Base user credential schema"""

    credential_data: Dict[str, Any] = Field(
        ...,
        description="Protocol-specific credentials (e.g., username, password, UUID, port)",
    )
    server_location: Optional[str] = Field(None, max_length=100)


class UserCredentialCreate(UserCredentialBase):
    """Schema for credential creation"""

    user_id: int
    subscription_id: int
    protocol_id: int


class UserCredentialUpdate(BaseModel):
    """Schema for credential updates"""

    credential_data: Optional[Dict[str, Any]] = None
    server_location: Optional[str] = Field(None, max_length=100)


class UserCredentialResponse(UserCredentialBase):
    """Schema for credential in responses"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    subscription_id: int
    protocol_id: int
    created_at: datetime
    updated_at: datetime


class UserCredentialWithProtocol(UserCredentialResponse):
    """Credential response with protocol details"""

    protocol_name: str
    protocol_display_name: Optional[str]


class CredentialDisplay(BaseModel):
    """User-friendly credential display format"""

    protocol: str
    server_location: str
    connection_string: str = Field(..., description="Ready-to-use connection string")
    qr_code: Optional[str] = Field(None, description="QR code for easy import")
    manual_config: Dict[str, Any] = Field(
        ..., description="Manual configuration details"
    )


# ============================================================================
# PROTOCOL ASSIGNMENT SCHEMAS
# ============================================================================


class UserProtocolAssignmentBase(BaseModel):
    """Base protocol assignment schema"""

    protocol_id: int
    instance_id: int


class UserProtocolAssignmentCreate(UserProtocolAssignmentBase):
    """Schema for protocol assignment creation"""

    user_id: int
    subscription_id: int


class UserProtocolAssignmentResponse(UserProtocolAssignmentBase):
    """Schema for protocol assignment in responses"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    subscription_id: int
    assigned_at: datetime


class UserProtocolAssignmentWithDetails(UserProtocolAssignmentResponse):
    """Protocol assignment with instance details"""

    instance_ip: str
    instance_country: str
    instance_city: Optional[str]
    protocol_name: str
