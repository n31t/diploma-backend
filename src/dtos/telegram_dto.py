"""
Telegram Data Transfer Objects.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class TelegramConnectDTO:
    """URL returned to the frontend so the user can open the bot."""
    bot_url: str


@dataclass
class TelegramStatusDTO:
    """Current Telegram connection state for a user."""
    is_connected: bool
    telegram_chat_id: Optional[str] = None