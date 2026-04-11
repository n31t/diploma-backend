"""Command /premium."""

from __future__ import annotations

from aiogram import Dispatcher
from aiogram.filters import Command
from aiogram.types import Message

from src.core.logging import get_logger
from src.telegram_bot.errors import reply_error_message
from src.telegram_bot.formatting import format_premium_screen
from src.telegram_bot.i18n import t
from src.telegram_bot.keyboards import premium_inline
from src.telegram_bot.locale_utils import map_fallback_locale
from src.telegram_bot.preferences import effective_ui_locale
from src.telegram_bot.urlutil import url_allowed_for_telegram_inline_button

logger = get_logger(__name__)


async def answer_premium(svc, message: Message) -> None:
    chat_id = str(message.chat.id)
    lc = message.from_user.language_code if message.from_user else None
    billing_url = f"{svc._config.FRONTEND_URL.rstrip('/')}/dashboard/billing"
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
            limits = await ctx.ai_detection.get_user_limits(user.id)
            upgrade_url: str | None = None
            manage_url: str | None = None
            if svc._config.STRIPE_SECRET_KEY and svc._config.STRIPE_PRICE_ID:
                try:
                    upgrade_url = await ctx.stripe.create_checkout_session(
                        user.id, user.email
                    )
                except Exception as exc:
                    logger.warning("telegram_checkout_fail", error=str(exc))
                if user.stripe_customer_id:
                    try:
                        manage_url = await ctx.stripe.create_portal_session(user.id)
                    except Exception as exc:
                        logger.warning("telegram_portal_fail", error=str(exc))
            await session.commit()
            text = format_premium_screen(loc, limits)
            if not url_allowed_for_telegram_inline_button(billing_url):
                text += "\n\n" + t("premium.billing_plain", loc, url=billing_url)
            kb = premium_inline(
                loc,
                upgrade_url=upgrade_url,
                manage_url=manage_url,
                billing_page_url=billing_url,
            )
            await message.answer(text, parse_mode="HTML", reply_markup=kb)
    except Exception as exc:
        logger.error("telegram_premium_error", error=str(exc), exc_info=True)
        loc = map_fallback_locale(lc)
        await reply_error_message(message, loc, "error.system.generic")


def register(dp: Dispatcher, svc) -> None:
    @dp.message(Command("premium"))
    async def handle_premium(message: Message) -> None:
        await answer_premium(svc, message)
