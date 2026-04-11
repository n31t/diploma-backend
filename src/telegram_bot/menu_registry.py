"""
Single registry: reply keyboard button label → internal menu action key.

Built once at import from i18n strings for all supported UI locales.
"""

from __future__ import annotations

from src.telegram_bot.i18n import SUPPORTED_UI_LOCALES, t

# Keys used for routing in handlers (must match i18n keys under menu.*).
MENU_ROUTING_KEYS: tuple[str, ...] = (
    "menu.analyze_text",
    "menu.analyze_file",
    "menu.analyze_url",
    "menu.my_stats",
    "menu.history",
    "menu.usage",
    "menu.premium",
    "menu.settings",
    "menu.help",
)


def _build_menu_action_by_text() -> dict[str, str]:
    out: dict[str, str] = {}
    for key in MENU_ROUTING_KEYS:
        for loc in SUPPORTED_UI_LOCALES:
            label = t(key, loc)
            out[label] = key
    return out


# Exact button text → i18n menu key (e.g. menu.analyze_text).
MENU_ACTION_BY_TEXT: dict[str, str] = _build_menu_action_by_text()
