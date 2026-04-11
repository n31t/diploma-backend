"""Dictionary-based i18n for Telegram bot (ru / kk / en)."""

from __future__ import annotations

from typing import Any

from src.telegram_bot.locales.catalog import MESSAGES, resolve_key

SUPPORTED_UI_LOCALES: tuple[str, ...] = ("ru", "kk", "en")


def t(key: str, locale: str, **kwargs: Any) -> str:
    loc = locale if locale in MESSAGES else "en"
    real_key = resolve_key(key)
    template = MESSAGES[loc].get(real_key) or MESSAGES["en"].get(real_key) or real_key
    try:
        return template.format(**kwargs)
    except Exception:
        return template


def result_label(result_value: str, locale: str) -> str:
    mapping = {
        "ai_generated": "result.ai",
        "human_written": "result.human",
        "uncertain": "result.uncertain",
    }
    return t(mapping.get(result_value, "result.uncertain"), locale)


def verdict_sentence(result_value: str, locale: str) -> str:
    mapping = {
        "ai_generated": "result.verdict_ai",
        "human_written": "result.verdict_human",
        "uncertain": "result.verdict_uncertain",
    }
    return t(mapping.get(result_value, "result.verdict_uncertain"), locale)
