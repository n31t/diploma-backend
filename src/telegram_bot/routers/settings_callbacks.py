"""Settings UI, language callbacks, /lang, navigation callbacks."""

from __future__ import annotations

from aiogram import Dispatcher, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from src.core.logging import get_logger
from src.telegram_bot.errors import reply_error_message
from src.telegram_bot.fsm import SettingsFsm
from src.telegram_bot.i18n import SUPPORTED_UI_LOCALES, t
from src.telegram_bot.keyboards import (
    main_menu_reply,
    ml_lang_inline,
    settings_root_inline,
    ui_lang_inline,
)
from src.telegram_bot.locale_utils import map_fallback_locale
from src.telegram_bot.preferences import effective_ui_locale

logger = get_logger(__name__)

_UI = frozenset(SUPPORTED_UI_LOCALES)
_ML = frozenset({"ru", "kk", "auto"})


def register(dp: Dispatcher, svc) -> None:
    @dp.message(Command("lang"))
    async def handle_lang(message: Message, state: FSMContext) -> None:
        chat_id = str(message.chat.id)
        lc = message.from_user.language_code if message.from_user else None
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2:
            async with svc._session_factory() as session:
                ctx = svc._build_ctx(session)
                user = await ctx.auth.get_user_by_telegram_chat_id(chat_id)
                loc = effective_ui_locale(user, lc) if user else map_fallback_locale(lc)
                await message.answer(
                    t("lang.bad", loc),
                    reply_markup=ml_lang_inline(loc),
                )
            return
        arg = parts[1].strip().lower()
        if arg == "kz":
            arg = "kk"
        if arg not in _ML:
            async with svc._session_factory() as session:
                ctx = svc._build_ctx(session)
                user = await ctx.auth.get_user_by_telegram_chat_id(chat_id)
                loc = effective_ui_locale(user, lc) if user else map_fallback_locale(lc)
                await message.answer(t("lang.bad", loc))
            return
        try:
            async with svc._session_factory() as session:
                ctx = svc._build_ctx(session)
                user = await ctx.auth.get_user_by_telegram_chat_id(chat_id)
                if not user:
                    await message.answer(t("error.not_linked", map_fallback_locale(lc)))
                    return
                await ctx.auth.set_telegram_detection_language(user.id, arg)
                await session.commit()
                user = await ctx.auth.get_user_by_id(user.id)
                loc = effective_ui_locale(user, lc)
                await message.answer(t("settings.det.saved", loc, code=arg))
        except Exception as exc:
            logger.error("telegram_lang_error", error=str(exc), exc_info=True)
            loc = map_fallback_locale(lc)
            await reply_error_message(message, loc, "error.system.generic")

    @dp.callback_query(F.data == "set:ui")
    async def open_ui_settings(query: CallbackQuery, state: FSMContext) -> None:
        await state.set_state(SettingsFsm.ui_lang)
        if not query.message:
            return
        chat_id = str(query.message.chat.id)
        lc = query.from_user.language_code if query.from_user else None
        async with svc._session_factory() as session:
            ctx = svc._build_ctx(session)
            user = await ctx.auth.get_user_by_telegram_chat_id(chat_id)
            loc = effective_ui_locale(user, lc) if user else map_fallback_locale(lc)
        text = f"{t('settings.ui_title', loc)}\n{t('settings.ui_intro', loc)}"
        await query.answer()
        try:
            await query.message.edit_text(text, reply_markup=ui_lang_inline(loc))
        except Exception:
            await query.message.answer(text, reply_markup=ui_lang_inline(loc))

    @dp.callback_query(F.data == "set:ml")
    async def open_ml_settings(query: CallbackQuery, state: FSMContext) -> None:
        await state.set_state(SettingsFsm.det_lang)
        if not query.message:
            return
        chat_id = str(query.message.chat.id)
        lc = query.from_user.language_code if query.from_user else None
        async with svc._session_factory() as session:
            ctx = svc._build_ctx(session)
            user = await ctx.auth.get_user_by_telegram_chat_id(chat_id)
            loc = effective_ui_locale(user, lc) if user else map_fallback_locale(lc)
        text = f"{t('settings.det_title', loc)}\n{t('settings.det_intro', loc)}"
        await query.answer()
        try:
            await query.message.edit_text(text, reply_markup=ml_lang_inline(loc))
        except Exception:
            await query.message.answer(text, reply_markup=ml_lang_inline(loc))

    @dp.callback_query(F.data == "nav:back:set")
    async def nav_back_settings(query: CallbackQuery, state: FSMContext) -> None:
        await state.set_state(SettingsFsm.main)
        if not query.message:
            return
        chat_id = str(query.message.chat.id)
        lc = query.from_user.language_code if query.from_user else None
        async with svc._session_factory() as session:
            ctx = svc._build_ctx(session)
            user = await ctx.auth.get_user_by_telegram_chat_id(chat_id)
            loc = effective_ui_locale(user, lc) if user else map_fallback_locale(lc)
        text = f"{t('settings.main_title', loc)}\n{t('settings.main_intro', loc)}"
        await query.answer()
        try:
            await query.message.edit_text(text, reply_markup=settings_root_inline(loc))
        except Exception:
            await query.message.answer(text, reply_markup=settings_root_inline(loc))

    @dp.callback_query(F.data == "nav:home")
    async def nav_home(query: CallbackQuery, state: FSMContext) -> None:
        await state.clear()
        if not query.message:
            return
        chat_id = str(query.message.chat.id)
        lc = query.from_user.language_code if query.from_user else None
        async with svc._session_factory() as session:
            ctx = svc._build_ctx(session)
            user = await ctx.auth.get_user_by_telegram_chat_id(chat_id)
            loc = effective_ui_locale(user, lc) if user else map_fallback_locale(lc)
        await query.answer()
        await query.message.answer(
            t("start.linked_hint", loc),
            reply_markup=main_menu_reply(loc),
        )

    @dp.callback_query(lambda q: bool(q.data and q.data.startswith("uil:") and q.data[4:] in _UI))
    async def handle_uil_cb(query: CallbackQuery, state: FSMContext) -> None:
        await state.set_state(SettingsFsm.main)
        if not query.data or not query.message:
            return
        loc_new = query.data.split(":", 1)[1]
        chat_id = str(query.message.chat.id)
        lc = query.from_user.language_code if query.from_user else None
        try:
            async with svc._session_factory() as session:
                ctx = svc._build_ctx(session)
                user = await ctx.auth.get_user_by_telegram_chat_id(chat_id)
                if not user:
                    loc = map_fallback_locale(lc)
                    await query.answer(t("error.not_linked", loc), show_alert=True)
                    return
                await ctx.auth.set_telegram_ui_locale(user.id, loc_new)
                await session.commit()
                await query.message.answer(
                    t("settings.ui.saved", loc_new, code=loc_new.upper()),
                    reply_markup=main_menu_reply(loc_new),
                )
            await query.answer()
        except Exception:
            loc = map_fallback_locale(lc)
            await query.answer(t("error.system.generic", loc), show_alert=True)

    @dp.callback_query(lambda q: bool(q.data and q.data.startswith("mll:") and q.data[4:] in _ML))
    async def handle_mll_cb(query: CallbackQuery, state: FSMContext) -> None:
        await state.set_state(SettingsFsm.main)
        if not query.data or not query.message:
            return
        lang = query.data.split(":", 1)[1]
        chat_id = str(query.message.chat.id)
        lc = query.from_user.language_code if query.from_user else None
        try:
            async with svc._session_factory() as session:
                ctx = svc._build_ctx(session)
                user = await ctx.auth.get_user_by_telegram_chat_id(chat_id)
                if not user:
                    loc = map_fallback_locale(lc)
                    await query.answer(t("error.not_linked", loc), show_alert=True)
                    return
                loc = effective_ui_locale(user, query.from_user.language_code if query.from_user else None)
                await ctx.auth.set_telegram_detection_language(user.id, lang)
                await session.commit()
                await query.message.answer(
                    t("settings.det.saved", loc, code=lang),
                    reply_markup=main_menu_reply(loc),
                )
            await query.answer()
        except Exception:
            loc = map_fallback_locale(lc)
            await query.answer(t("error.system.generic", loc), show_alert=True)
