"""Resolve Telegram user preferences for ML language and UI locale."""

from __future__ import annotations

from src.api.v1.schemas.detection_language import (
    DetectionLanguageContext,
    context_from_api_language,
)
from src.models.auth import User
from src.repositories.auth_repository import map_telegram_language_code_to_ui_locale

SUPPORTED_UI_LOCALES = frozenset({"ru", "kk", "en"})
SUPPORTED_ML_LANGS = frozenset({"ru", "kk", "auto"})


def detection_language_context_from_user(user: User) -> DetectionLanguageContext:
    """Build ML routing context from stored telegram_detection_language."""
    raw = (user.telegram_detection_language or "auto").strip().lower()
    if raw not in SUPPORTED_ML_LANGS:
        raw = "auto"
    return context_from_api_language(raw)  # type: ignore[arg-type]


def effective_ui_locale(user: User, telegram_language_code: str | None) -> str:
    """Prefer persisted UI locale; else map Telegram client language."""
    if user.telegram_ui_locale and user.telegram_ui_locale in SUPPORTED_UI_LOCALES:
        return user.telegram_ui_locale
    return map_telegram_language_code_to_ui_locale(telegram_language_code)
