"""
Map exceptions to stable i18n keys — never expose raw exception strings to users.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from aiogram.types import CallbackQuery, Message

from src.dtos.rate_limit_dto import RateLimitExceeded
from src.services.ml_model_service import KazakhMlApiUnavailableError
from src.telegram_bot.i18n import t


class ErrorKind(str, Enum):
    USER_INPUT = "user"
    LIMIT = "limit"
    EXTERNAL = "external"
    SYSTEM = "system"


def i18n_key_for_exception(exc: BaseException) -> tuple[str, dict[str, Any]]:
    """
    Return (i18n_key, format_kwargs) for t().
    Unknown errors map to error.system.generic with no exception text.
    """
    if isinstance(exc, RateLimitExceeded):
        return "error.limit.rate", {"retry": exc.retry_after}
    if isinstance(exc, KazakhMlApiUnavailableError):
        return "error.external.ml_unavailable", {}
    if isinstance(exc, ValueError):
        msg = str(exc).lower()
        if "limit exceeded" in msg or "request limit" in msg or "quota" in msg:
            return "error.limit.quota", {}
        if "too short" in msg or "minimum" in msg:
            return "error.user.short_text", {}
        if "url" in msg and ("invalid" in msg or "http" in msg):
            return "error.user.url_invalid", {}
        return "error.user.validation", {}
    if isinstance(exc, RuntimeError):
        return "error.system.generic", {}
    return "error.system.generic", {}


def kind_for_exception(exc: BaseException) -> ErrorKind:
    if isinstance(exc, (RateLimitExceeded,)) or (
        isinstance(exc, ValueError) and "limit" in str(exc).lower()
    ):
        return ErrorKind.LIMIT
    if isinstance(exc, KazakhMlApiUnavailableError):
        return ErrorKind.EXTERNAL
    if isinstance(exc, ValueError):
        return ErrorKind.USER_INPUT
    return ErrorKind.SYSTEM


async def reply_error_message(
    message: Message,
    locale: str,
    key: str,
    *,
    parse_mode: str | None = "HTML",
    **kwargs: Any,
) -> None:
    await message.answer(t(key, locale, **kwargs), parse_mode=parse_mode)


async def reply_error_query(
    query: CallbackQuery,
    locale: str,
    key: str,
    *,
    show_alert: bool = True,
    **kwargs: Any,
) -> None:
    await query.answer(t(key, locale, **kwargs), show_alert=show_alert)
