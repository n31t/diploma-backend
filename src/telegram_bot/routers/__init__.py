"""Register aiogram routers on the Telegram dispatcher."""

from __future__ import annotations

from aiogram import Dispatcher

from src.telegram_bot.routers import analyze, premium, settings_callbacks, start_help, usage_stats_history


def register_telegram_routers(dp: Dispatcher, svc) -> None:
    start_help.register(dp, svc)
    usage_stats_history.register(dp, svc)
    premium.register(dp, svc)
    settings_callbacks.register(dp, svc)
    analyze.register(dp, svc)
