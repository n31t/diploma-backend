"""Commands: /start, /help, /disconnect."""

from __future__ import annotations

from aiogram import Dispatcher
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from src.core.gemini_config import gemini_config
from src.core.logging import get_logger
from src.repositories.auth_repository import AuthRepository
from src.telegram_bot.errors import reply_error_message
from src.telegram_bot.i18n import t
from src.telegram_bot.keyboards import main_menu_reply
from src.telegram_bot.locale_utils import map_fallback_locale
from src.telegram_bot.preferences import effective_ui_locale

logger = get_logger(__name__)


async def answer_help(svc, message: Message) -> None:
    chat_id = str(message.chat.id)
    lc = message.from_user.language_code if message.from_user else None
    async with svc._session_factory() as session:
        ctx = svc._build_ctx(session)
        user = await ctx.auth.get_user_by_telegram_chat_id(chat_id)
        loc = effective_ui_locale(user, lc) if user else map_fallback_locale(lc)
        await message.answer(
            t(
                "help.body",
                loc,
                max_mb=gemini_config.MAX_FILE_SIZE_MB,
            ),
            parse_mode="HTML",
            reply_markup=main_menu_reply(loc),
        )


def register(dp: Dispatcher, svc) -> None:
    @dp.message(Command("start"))
    async def handle_start(message: Message, state: FSMContext) -> None:
        await state.clear()
        parts = (message.text or "").split(maxsplit=1)
        chat_id = str(message.chat.id)
        lc = message.from_user.language_code if message.from_user else None

        if len(parts) < 2:
            async with svc._session_factory() as session:
                repo = AuthRepository(session)
                u = await repo.get_user_by_telegram_chat_id(chat_id)
                loc = effective_ui_locale(u, lc) if u else map_fallback_locale(lc)
                if u:
                    await message.answer(
                        t("start.connected", loc) + "\n\n" + t("start.linked_hint", loc),
                        reply_markup=main_menu_reply(loc),
                    )
                else:
                    await message.answer(
                        t("start.cta_unlinked", loc) + "\n\n" + t("start.welcome", loc),
                    )
            return

        token = parts[1].strip()
        try:
            async with svc._session_factory() as session:
                repo = AuthRepository(session)
                user = await repo.get_user_by_telegram_token(token)
                if not user:
                    u0 = await repo.get_user_by_telegram_chat_id(chat_id)
                    loc = effective_ui_locale(u0, lc) if u0 else map_fallback_locale(lc)
                    await message.answer(t("start.bad_token", loc))
                    return

                existing = await repo.get_user_by_telegram_chat_id(chat_id)
                if existing:
                    loc = effective_ui_locale(existing, lc)
                    if existing.id == user.id:
                        await message.answer(
                            t("start.connected", loc),
                            reply_markup=main_menu_reply(loc),
                        )
                    else:
                        await message.answer(t("start.other_user", loc))
                    return

                await repo.connect_telegram_account(user.id, chat_id)
                await repo.ensure_telegram_ui_locale_from_client(user.id, lc)
                user = await repo.get_user_by_id(user.id)
                await session.commit()
                loc = effective_ui_locale(user, lc) if user else map_fallback_locale(lc)
                supported = ", ".join(sorted(gemini_config.ALLOWED_FILE_EXTENSIONS))
                await message.answer(
                    t("start.success", loc, formats=supported)
                    + "\n\n"
                    + t("start.linked_hint", loc),
                    reply_markup=main_menu_reply(loc),
                )
                logger.info(
                    "telegram_account_connected",
                    user_id=user.id,
                    chat_id=chat_id,
                )
        except Exception as exc:
            logger.error("telegram_start_error", error=str(exc), exc_info=True)
            loc = map_fallback_locale(lc)
            await reply_error_message(message, loc, "error.system.connect")

    @dp.message(Command("help"))
    async def handle_help(message: Message, state: FSMContext) -> None:
        await state.clear()
        await answer_help(svc, message)

    @dp.message(Command("disconnect"))
    async def handle_disconnect(message: Message, state: FSMContext) -> None:
        await state.clear()
        chat_id = str(message.chat.id)
        lc = message.from_user.language_code if message.from_user else None
        try:
            async with svc._session_factory() as session:
                ctx = svc._build_ctx(session)
                user = await ctx.auth.get_user_by_telegram_chat_id(chat_id)
                if not user:
                    await message.answer(
                        t("disconnect.not_linked", map_fallback_locale(lc)),
                    )
                    return
                loc = effective_ui_locale(user, lc)
                await ctx.auth.disconnect_telegram(user.id)
                await session.commit()
                await message.answer(t("disconnect.ok", loc))
        except Exception as exc:
            logger.error("telegram_disconnect_error", error=str(exc), exc_info=True)
            loc = map_fallback_locale(lc)
            await reply_error_message(message, loc, "error.system.disconnect")
