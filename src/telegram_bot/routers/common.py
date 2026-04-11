"""Shared helpers for Telegram routers (thin re-exports)."""

from __future__ import annotations

from src.telegram_bot.errors import reply_error_message
from src.telegram_bot.locale_utils import locale_for_chat, map_fallback_locale

__all__ = [
    "locale_for_chat",
    "map_fallback_locale",
    "reply_error_message",
]
