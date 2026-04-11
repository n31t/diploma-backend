"""Commands: /limits, /usage, /stats, /history; history pagination callback."""

from __future__ import annotations

from aiogram import Dispatcher
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from src.core.logging import get_logger
from src.telegram_bot.errors import reply_error_message
from src.telegram_bot.formatting import format_history_page, format_stats, format_usage_card
from src.telegram_bot.i18n import t
from src.telegram_bot.keyboards import history_next_inline, nav_home_row
from src.telegram_bot.locale_utils import locale_for_chat, map_fallback_locale
from src.telegram_bot.preferences import effective_ui_locale

logger = get_logger(__name__)

PAGE_SIZE = 5


async def _history_payload(
    svc,
    chat_id: str,
    lc: str | None,
    offset: int,
) -> tuple[str | None, InlineKeyboardMarkup | None, str]:
    async with svc._session_factory() as session:
        ctx = svc._build_ctx(session)
        user = await ctx.auth.get_user_by_telegram_chat_id(chat_id)
        if not user:
            return None, None, map_fallback_locale(lc)
        await ctx.auth.ensure_telegram_ui_locale_from_client(user.id, lc)
        user = await ctx.auth.get_user_by_id(user.id)
        loc = effective_ui_locale(user, lc)
        rows = await ctx.ai_repo.get_user_history(
            user.id, limit=PAGE_SIZE + 1, offset=offset
        )
        has_more = len(rows) > PAGE_SIZE
        rows = rows[:PAGE_SIZE]
        text = format_history_page(rows, loc, offset)
        if has_more:
            kb = history_next_inline(loc, offset + PAGE_SIZE)
        else:
            kb = InlineKeyboardMarkup(inline_keyboard=[nav_home_row(loc)])
        return text, kb, loc


def register(dp: Dispatcher, svc) -> None:
    @dp.message(Command("limits"))
    @dp.message(Command("usage"))
    async def handle_usage(message: Message) -> None:
        chat_id = str(message.chat.id)
        lc = message.from_user.language_code if message.from_user else None
        try:
            async with svc._session_factory() as session:
                ctx = svc._build_ctx(session)
                user = await ctx.auth.get_user_by_telegram_chat_id(chat_id)
                if not user:
                    await message.answer(t("error.not_linked", map_fallback_locale(lc)))
                    return
                await ctx.auth.ensure_telegram_ui_locale_from_client(user.id, lc)
                user = await ctx.auth.get_user_by_id(user.id)
                loc = effective_ui_locale(user, lc)
                dto = await ctx.ai_detection.get_user_limits(user.id)
                await message.answer(format_usage_card(dto, loc), parse_mode="HTML")
        except Exception as exc:
            logger.error("telegram_limits_error", error=str(exc), exc_info=True)
            loc = await locale_for_chat(svc, message)
            await reply_error_message(message, loc, "error.system.generic")

    @dp.message(Command("stats"))
    async def handle_stats(message: Message) -> None:
        chat_id = str(message.chat.id)
        lc = message.from_user.language_code if message.from_user else None
        try:
            async with svc._session_factory() as session:
                ctx = svc._build_ctx(session)
                user = await ctx.auth.get_user_by_telegram_chat_id(chat_id)
                if not user:
                    await message.answer(t("error.not_linked", map_fallback_locale(lc)))
                    return
                await ctx.auth.ensure_telegram_ui_locale_from_client(user.id, lc)
                user = await ctx.auth.get_user_by_id(user.id)
                loc = effective_ui_locale(user, lc)
                stats = await ctx.ai_repo.get_user_stats(user.id)
                await message.answer(format_stats(stats, loc), parse_mode="HTML")
        except Exception as exc:
            logger.error("telegram_stats_error", error=str(exc), exc_info=True)
            loc = await locale_for_chat(svc, message)
            await reply_error_message(message, loc, "error.system.generic")

    @dp.message(Command("history"))
    async def handle_history(message: Message) -> None:
        chat_id = str(message.chat.id)
        lc = message.from_user.language_code if message.from_user else None
        try:
            text, kb, floc = await _history_payload(svc, chat_id, lc, 0)
            if text is None:
                await message.answer(t("error.not_linked", floc))
                return
            await message.answer(text, parse_mode="HTML", reply_markup=kb)
        except Exception as exc:
            logger.error("telegram_history_error", error=str(exc), exc_info=True)
            loc = await locale_for_chat(svc, message)
            await reply_error_message(message, loc, "error.system.generic")

    @dp.callback_query(lambda q: bool(q.data and q.data.startswith("h:") and q.data[2:].isdigit()))
    async def handle_hist_cb(query: CallbackQuery) -> None:
        if not query.data or not query.message:
            return
        offset = int(query.data.split(":", 1)[1])
        chat_id = str(query.message.chat.id)
        lc = query.from_user.language_code if query.from_user else None
        await query.answer()
        try:
            text, kb, floc = await _history_payload(svc, chat_id, lc, offset)
            if text is None:
                await query.answer(t("error.not_linked", floc), show_alert=True)
                return
            try:
                await query.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
            except Exception:
                await query.message.answer(text, parse_mode="HTML", reply_markup=kb)
        except Exception as exc:
            logger.error("telegram_history_cb_error", error=str(exc), exc_info=True)
            loc = map_fallback_locale(lc)
            await query.answer(t("error.system.generic", loc), show_alert=True)
