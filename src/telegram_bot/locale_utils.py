"""Telegram client language → UI locale helpers."""

from __future__ import annotations

from aiogram.types import Message

from src.repositories.auth_repository import map_telegram_language_code_to_ui_locale
from src.telegram_bot.preferences import effective_ui_locale


def map_fallback_locale(telegram_code: str | None) -> str:
    return map_telegram_language_code_to_ui_locale(telegram_code)


async def locale_for_chat(svc, message: Message) -> str:
    """Resolve stored UI locale for this chat, or Telegram client fallback."""
    chat_id = str(message.chat.id)
    lc = message.from_user.language_code if message.from_user else None
    async with svc._session_factory() as session:
        ctx = svc._build_ctx(session)
        user = await ctx.auth.get_user_by_telegram_chat_id(chat_id)
        if not user:
            return map_fallback_locale(lc)
        return effective_ui_locale(user, lc)
