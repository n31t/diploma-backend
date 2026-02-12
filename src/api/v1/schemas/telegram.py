"""
Pydantic schemas for Telegram integration API.
"""

from typing import Optional
from pydantic import BaseModel, Field


class TelegramConnectResponse(BaseModel):
    """Response schema for generating a Telegram connection URL."""

    bot_url: str = Field(..., description="Deep-link URL to open the bot with an auth token")

    class Config:
        json_schema_extra = {
            "example": {
                "bot_url": "https://t.me/mybot?start=abc123def456"
            }
        }


class TelegramStatusResponse(BaseModel):
    """Response schema for Telegram connection status."""

    is_connected: bool = Field(..., description="Whether a Telegram account is linked")
    telegram_chat_id: Optional[str] = Field(None, description="Linked Telegram chat ID (masked)")

    class Config:
        json_schema_extra = {
            "example": {
                "is_connected": True,
                "telegram_chat_id": "123456789"
            }
        }