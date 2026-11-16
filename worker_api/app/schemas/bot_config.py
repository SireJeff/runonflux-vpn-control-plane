"""Request/response schemas for the bot-config endpoints."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class BotConfigUpsertRequest(BaseModel):
    bot_token: str = Field(..., min_length=20, description="Token from @BotFather")
    bot_display_name: Optional[str] = Field(None, max_length=100)
    welcome_message_fa: Optional[str] = None
    welcome_message_en: Optional[str] = None
    card_number: Optional[str] = Field(None, max_length=20)
    card_holder_name: Optional[str] = Field(None, max_length=100)
    crypto_address: Optional[str] = Field(None, max_length=255)
    crypto_network: Optional[str] = Field(None, max_length=50)
    crypto_memo: Optional[str] = Field(None, max_length=255)
    support_phone: Optional[str] = Field(None, max_length=20)
    support_telegram: Optional[str] = Field(None, max_length=50)
    default_macro_region: str = Field("eu", max_length=5)


class BotConfigResponse(BaseModel):
    id: int
    admin_id: int
    bot_username: str
    bot_user_id: int
    bot_display_name: Optional[str]
    welcome_message_fa: Optional[str]
    welcome_message_en: Optional[str]
    card_number: Optional[str]
    card_holder_name: Optional[str]
    crypto_address: Optional[str]
    crypto_network: Optional[str]
    crypto_memo: Optional[str]
    support_phone: Optional[str]
    support_telegram: Optional[str]
    default_macro_region: str
    is_active: bool
    webhook_registered_at: Optional[datetime]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BotConfigUpdateRequest(BaseModel):
    """All fields optional -- used for PUT updates that don't rotate token."""

    bot_display_name: Optional[str] = None
    welcome_message_fa: Optional[str] = None
    welcome_message_en: Optional[str] = None
    card_number: Optional[str] = None
    card_holder_name: Optional[str] = None
    crypto_address: Optional[str] = None
    crypto_network: Optional[str] = None
    crypto_memo: Optional[str] = None
    support_phone: Optional[str] = None
    support_telegram: Optional[str] = None
    default_macro_region: Optional[str] = None
