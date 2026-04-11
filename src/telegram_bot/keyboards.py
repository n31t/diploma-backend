"""Reply and inline keyboards for Telegram bot."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

from src.telegram_bot.i18n import t
from src.telegram_bot.urlutil import url_allowed_for_telegram_inline_button


def main_menu_reply(locale: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=t("menu.analyze_text", locale)),
                KeyboardButton(text=t("menu.analyze_file", locale)),
                KeyboardButton(text=t("menu.analyze_url", locale)),
            ],
            [
                KeyboardButton(text=t("menu.my_stats", locale)),
                KeyboardButton(text=t("menu.history", locale)),
                KeyboardButton(text=t("menu.usage", locale)),
            ],
            [
                KeyboardButton(text=t("menu.premium", locale)),
                KeyboardButton(text=t("menu.settings", locale)),
                KeyboardButton(text=t("menu.help", locale)),
            ],
        ],
        resize_keyboard=True,
    )


def nav_home_row(locale: str) -> list[InlineKeyboardButton]:
    return [
        InlineKeyboardButton(text=t("nav.home", locale), callback_data="nav:home"),
    ]


def settings_root_inline(locale: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("settings.ui_button", locale),
                    callback_data="set:ui",
                ),
                InlineKeyboardButton(
                    text=t("settings.det_button", locale),
                    callback_data="set:ml",
                ),
            ],
            nav_home_row(locale),
        ]
    )


def ui_lang_inline(locale: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="RU", callback_data="uil:ru"),
                InlineKeyboardButton(text="KK", callback_data="uil:kk"),
                InlineKeyboardButton(text="EN", callback_data="uil:en"),
            ],
            [
                InlineKeyboardButton(text=t("nav.back", locale), callback_data="nav:back:set"),
            ],
            nav_home_row(locale),
        ]
    )


def ml_lang_inline(locale: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="ru", callback_data="mll:ru"),
                InlineKeyboardButton(text="kk", callback_data="mll:kk"),
                InlineKeyboardButton(text="auto", callback_data="mll:auto"),
            ],
            [
                InlineKeyboardButton(text=t("nav.back", locale), callback_data="nav:back:set"),
            ],
            nav_home_row(locale),
        ]
    )


def history_next_inline(
    locale: str,
    next_offset: int,
    *,
    include_nav: bool = True,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text=t("history.next", locale),
                callback_data=f"h:{next_offset}",
            )
        ]
    ]
    if include_nav:
        rows.append(nav_home_row(locale))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def premium_inline(
    locale: str,
    upgrade_url: str | None,
    manage_url: str | None,
    billing_page_url: str,
) -> InlineKeyboardMarkup:
    """Build keyboard only with Telegram-accepted URLs (not localhost, etc.)."""
    rows: list[list[InlineKeyboardButton]] = []
    if upgrade_url and url_allowed_for_telegram_inline_button(upgrade_url):
        rows.append(
            [
                InlineKeyboardButton(
                    text=t("premium.upgrade", locale),
                    url=upgrade_url,
                )
            ]
        )
    if manage_url and url_allowed_for_telegram_inline_button(manage_url):
        rows.append(
            [
                InlineKeyboardButton(
                    text=t("premium.manage", locale),
                    url=manage_url,
                )
            ]
        )
    if url_allowed_for_telegram_inline_button(billing_page_url):
        rows.append(
            [
                InlineKeyboardButton(
                    text=t("premium.billing_page", locale),
                    url=billing_page_url,
                )
            ]
        )
    rows.append(nav_home_row(locale))
    return InlineKeyboardMarkup(inline_keyboard=rows)
