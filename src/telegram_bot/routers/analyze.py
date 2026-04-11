"""Text / file / photo / URL detection, reply keyboard menu routing, URL FSM."""

from __future__ import annotations

import os

from aiogram import Dispatcher, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Document, Message, PhotoSize

from src.core.gemini_config import gemini_config
from src.core.logging import get_logger
from src.dtos.rate_limit_dto import RateLimitExceeded
from src.services.ml_model_service import KazakhMlApiUnavailableError
from src.telegram_bot.errors import i18n_key_for_exception, reply_error_message
from src.telegram_bot.formatting import format_detection_result
from src.telegram_bot.fsm import AnalyzeFsm
from src.telegram_bot.i18n import t
from src.telegram_bot.keyboards import settings_root_inline
from src.telegram_bot.locale_utils import locale_for_chat, map_fallback_locale
from src.telegram_bot.menu_registry import MENU_ACTION_BY_TEXT
from src.telegram_bot.preferences import detection_language_context_from_user, effective_ui_locale
from src.telegram_bot.urlutil import validate_public_url

logger = get_logger(__name__)

SUPPORTED_EXTENSIONS: frozenset[str] = frozenset(gemini_config.ALLOWED_FILE_EXTENSIONS)


async def _route_reply_menu_action(
    svc,
    message: Message,
    state: FSMContext,
    text: str,
) -> bool:
    """If text matches a reply keyboard label, run menu logic and return True."""
    action = MENU_ACTION_BY_TEXT.get(text.strip())
    if action is None:
        return False

    if action == "menu.analyze_url":
        lc = await locale_for_chat(svc, message)
        await state.set_state(AnalyzeFsm.expecting_url)
        await message.answer(t("analyze.expecting_url", lc))
        return True

    await state.set_state(AnalyzeFsm.idle)

    if action == "menu.analyze_text":
        lc = await locale_for_chat(svc, message)
        await message.answer(t("analyze.hint_text", lc))
        return True
    if action == "menu.analyze_file":
        lc = await locale_for_chat(svc, message)
        await message.answer(t("analyze.hint_file", lc))
        return True
    if action == "menu.my_stats":
        from src.telegram_bot.formatting import format_stats

        chat_id = str(message.chat.id)
        lc = message.from_user.language_code if message.from_user else None
        try:
            async with svc._session_factory() as session:
                ctx = svc._build_ctx(session)
                user = await ctx.auth.get_user_by_telegram_chat_id(chat_id)
                if not user:
                    await message.answer(t("error.not_linked", map_fallback_locale(lc)))
                    return True
                await ctx.auth.ensure_telegram_ui_locale_from_client(user.id, lc)
                user = await ctx.auth.get_user_by_id(user.id)
                loc = effective_ui_locale(user, lc)
                stats = await ctx.ai_repo.get_user_stats(user.id)
                await message.answer(format_stats(stats, loc), parse_mode="HTML")
        except Exception as exc:
            logger.error("telegram_stats_menu_error", error=str(exc), exc_info=True)
            loc = await locale_for_chat(svc, message)
            await reply_error_message(message, loc, "error.system.generic")
        return True
    if action == "menu.history":
        from aiogram.types import InlineKeyboardMarkup

        from src.telegram_bot.formatting import format_history_page
        from src.telegram_bot.keyboards import history_next_inline, nav_home_row

        chat_id = str(message.chat.id)
        lc = message.from_user.language_code if message.from_user else None
        page_size = 5
        try:
            async with svc._session_factory() as session:
                ctx = svc._build_ctx(session)
                user = await ctx.auth.get_user_by_telegram_chat_id(chat_id)
                if not user:
                    await message.answer(t("error.not_linked", map_fallback_locale(lc)))
                    return True
                await ctx.auth.ensure_telegram_ui_locale_from_client(user.id, lc)
                user = await ctx.auth.get_user_by_id(user.id)
                loc = effective_ui_locale(user, lc)
                rows = await ctx.ai_repo.get_user_history(
                    user.id, limit=page_size + 1, offset=0
                )
                has_more = len(rows) > page_size
                rows = rows[:page_size]
                text_out = format_history_page(rows, loc, 0)
                kb = (
                    history_next_inline(loc, page_size)
                    if has_more
                    else InlineKeyboardMarkup(inline_keyboard=[nav_home_row(loc)])
                )
                await message.answer(text_out, parse_mode="HTML", reply_markup=kb)
        except Exception as exc:
            logger.error("telegram_history_menu_error", error=str(exc), exc_info=True)
            loc = await locale_for_chat(svc, message)
            await reply_error_message(message, loc, "error.system.generic")
        return True
    if action == "menu.usage":
        from src.telegram_bot.formatting import format_usage_card

        chat_id = str(message.chat.id)
        lc = message.from_user.language_code if message.from_user else None
        try:
            async with svc._session_factory() as session:
                ctx = svc._build_ctx(session)
                user = await ctx.auth.get_user_by_telegram_chat_id(chat_id)
                if not user:
                    await message.answer(t("error.not_linked", map_fallback_locale(lc)))
                    return True
                await ctx.auth.ensure_telegram_ui_locale_from_client(user.id, lc)
                user = await ctx.auth.get_user_by_id(user.id)
                loc = effective_ui_locale(user, lc)
                dto = await ctx.ai_detection.get_user_limits(user.id)
                await message.answer(format_usage_card(dto, loc), parse_mode="HTML")
        except Exception as exc:
            logger.error("telegram_usage_menu_error", error=str(exc), exc_info=True)
            loc = await locale_for_chat(svc, message)
            await reply_error_message(message, loc, "error.system.generic")
        return True
    if action == "menu.settings":
        lc = await locale_for_chat(svc, message)
        await message.answer(
            f"{t('settings.main_title', lc)}\n{t('settings.main_intro', lc)}",
            reply_markup=settings_root_inline(lc),
        )
        return True
    if action == "menu.premium":
        from src.telegram_bot.routers.premium import answer_premium

        await answer_premium(svc, message)
        return True
    if action == "menu.help":
        from src.telegram_bot.routers.start_help import answer_help

        await answer_help(svc, message)
        return True

    return False  # unreachable if MENU_ROUTING_KEYS and branches stay in sync


def register(dp: Dispatcher, svc) -> None:
    @dp.message(AnalyzeFsm.expecting_url, F.text)
    async def handle_expecting_url(message: Message, state: FSMContext) -> None:
        raw = (message.text or "").strip()
        if await _route_reply_menu_action(svc, message, state, raw):
            return
        await state.set_state(AnalyzeFsm.idle)
        if not raw:
            loc = await locale_for_chat(svc, message)
            await message.answer(t("error.user.url_invalid", loc))
            return
        try:
            url = validate_public_url(raw)
        except ValueError:
            loc = await locale_for_chat(svc, message)
            await message.answer(t("error.user.url_invalid", loc))
            return
        await _run_url_detection(svc, message, url)

    @dp.message(Command("url"))
    async def handle_url_cmd(message: Message, state: FSMContext) -> None:
        await state.set_state(AnalyzeFsm.idle)
        chat_id = str(message.chat.id)
        lc = message.from_user.language_code if message.from_user else None
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2:
            async with svc._session_factory() as session:
                ctx = svc._build_ctx(session)
                user = await ctx.auth.get_user_by_telegram_chat_id(chat_id)
                loc = effective_ui_locale(user, lc) if user else map_fallback_locale(lc)
                await message.answer(t("url.need", loc))
            return
        raw_url = parts[1].strip()
        try:
            url = validate_public_url(raw_url)
        except ValueError:
            async with svc._session_factory() as session:
                ctx = svc._build_ctx(session)
                user = await ctx.auth.get_user_by_telegram_chat_id(chat_id)
                loc = effective_ui_locale(user, lc) if user else map_fallback_locale(lc)
                await message.answer(t("url.bad", loc))
            return
        await _run_url_detection(svc, message, url)

    @dp.message(F.text & ~F.text.startswith("/"))
    async def handle_text_routing(message: Message, state: FSMContext) -> None:
        text = (message.text or "").strip()
        if await _route_reply_menu_action(svc, message, state, text):
            return
        await _handle_plain_text(svc, message, text)

    @dp.message(F.document)
    async def handle_document(message: Message, state: FSMContext) -> None:
        await state.set_state(AnalyzeFsm.idle)
        await _handle_document(svc, message)

    @dp.message(F.photo)
    async def handle_photo(message: Message, state: FSMContext) -> None:
        await state.set_state(AnalyzeFsm.idle)
        await _handle_photo(svc, message)

    @dp.message()
    async def handle_unknown(message: Message, state: FSMContext) -> None:
        await state.set_state(AnalyzeFsm.idle)
        lc = await locale_for_chat(svc, message)
        await message.answer(t("unknown", lc))


async def _run_url_detection(svc, message: Message, url: str) -> None:
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
            lang = detection_language_context_from_user(user)
            await svc._rate_check(ctx, user.id)
            await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
            result = await ctx.telegram_detection.detect_url(
                url=url, user_id=user.id, language=lang
            )
            await session.commit()
        await message.answer(
            format_detection_result(result, loc),
            parse_mode="HTML",
        )
    except RateLimitExceeded as exc:
        loc = await locale_for_chat(svc, message)
        await reply_error_message(message, loc, "error.limit.rate", retry=exc.retry_after)
    except KazakhMlApiUnavailableError:
        loc = await locale_for_chat(svc, message)
        await reply_error_message(message, loc, "error.external.ml_unavailable")
    except ValueError as exc:
        loc = await locale_for_chat(svc, message)
        key, kw = i18n_key_for_exception(exc)
        await reply_error_message(message, loc, key, **kw)
    except RuntimeError:
        loc = await locale_for_chat(svc, message)
        await reply_error_message(message, loc, "error.system.generic")
    except Exception as exc:
        logger.error("telegram_url_error", error=str(exc), exc_info=True)
        loc = await locale_for_chat(svc, message)
        await reply_error_message(message, loc, "error.system.generic")


async def _handle_plain_text(svc, message: Message, text: str) -> None:
    chat_id = str(message.chat.id)
    lc = message.from_user.language_code if message.from_user else None
    if len(text) < 50:
        async with svc._session_factory() as session:
            ctx = svc._build_ctx(session)
            user = await ctx.auth.get_user_by_telegram_chat_id(chat_id)
            loc = effective_ui_locale(user, lc) if user else map_fallback_locale(lc)
            await message.answer(t("error.user.short_text", loc, n=len(text)))
        return

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
            lang = detection_language_context_from_user(user)
            await svc._rate_check(ctx, user.id)
            await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
            result = await ctx.telegram_detection.detect_text(
                text=text, user_id=user.id, language=lang
            )
            await session.commit()
        await message.answer(
            format_detection_result(result, loc),
            parse_mode="HTML",
        )
        logger.info(
            "telegram_text_done",
            user_id=user.id,
            result=result.result.value,
        )
    except RateLimitExceeded as exc:
        loc = await locale_for_chat(svc, message)
        await reply_error_message(message, loc, "error.limit.rate", retry=exc.retry_after)
    except KazakhMlApiUnavailableError:
        loc = await locale_for_chat(svc, message)
        await reply_error_message(message, loc, "error.external.ml_unavailable")
    except ValueError as exc:
        loc = await locale_for_chat(svc, message)
        key, kw = i18n_key_for_exception(exc)
        await reply_error_message(message, loc, key, **kw)
    except Exception as exc:
        logger.error("telegram_text_error", error=str(exc), exc_info=True)
        loc = await locale_for_chat(svc, message)
        await reply_error_message(message, loc, "error.system.generic")


async def _handle_document(svc, message: Message) -> None:
    chat_id = str(message.chat.id)
    lc = message.from_user.language_code if message.from_user else None
    doc: Document = message.document
    file_name = doc.file_name or "document"
    ext = os.path.splitext(file_name)[1].lower()

    loc = await locale_for_chat(svc, message)
    if ext not in SUPPORTED_EXTENSIONS:
        await message.answer(t("error.file.unsupported_type", loc, ext=ext or "—"))
        return
    max_bytes = gemini_config.MAX_FILE_SIZE_MB * 1024 * 1024
    if doc.file_size and doc.file_size > max_bytes:
        await message.answer(
            t(
                "error.file.too_large",
                loc,
                size_mb=round(doc.file_size / 1024 / 1024, 1),
                max_mb=gemini_config.MAX_FILE_SIZE_MB,
            )
        )
        return

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
            lang = detection_language_context_from_user(user)
            await svc._rate_check(ctx, user.id)
            await message.bot.send_chat_action(
                chat_id=message.chat.id, action="upload_document"
            )
            file_bytes = await svc._download_bytes(doc.file_id)
            content_type = doc.mime_type or "application/octet-stream"
            result = await ctx.telegram_detection.detect_file(
                file_bytes=file_bytes,
                file_name=file_name,
                content_type=content_type,
                user_id=user.id,
                language=lang,
            )
            await session.commit()
        await message.answer(
            format_detection_result(result, loc),
            parse_mode="HTML",
        )
    except RateLimitExceeded as exc:
        loc = await locale_for_chat(svc, message)
        await reply_error_message(message, loc, "error.limit.rate", retry=exc.retry_after)
    except KazakhMlApiUnavailableError:
        loc = await locale_for_chat(svc, message)
        await reply_error_message(message, loc, "error.external.ml_unavailable")
    except ValueError as exc:
        loc = await locale_for_chat(svc, message)
        key, kw = i18n_key_for_exception(exc)
        await reply_error_message(message, loc, key, **kw)
    except RuntimeError:
        loc = await locale_for_chat(svc, message)
        await reply_error_message(message, loc, "error.system.generic")
    except Exception as exc:
        logger.error("telegram_file_error", error=str(exc), exc_info=True)
        loc = await locale_for_chat(svc, message)
        await reply_error_message(message, loc, "error.system.generic")


async def _handle_photo(svc, message: Message) -> None:
    chat_id = str(message.chat.id)
    lc = message.from_user.language_code if message.from_user else None
    photo: PhotoSize = message.photo[-1]
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
            lang = detection_language_context_from_user(user)
            await svc._rate_check(ctx, user.id)
            await message.bot.send_chat_action(
                chat_id=message.chat.id, action="upload_photo"
            )
            file_bytes = await svc._download_bytes(photo.file_id)
            file_name = f"photo_{photo.file_unique_id}.jpg"
            result = await ctx.telegram_detection.detect_image(
                image_bytes=file_bytes,
                file_name=file_name,
                user_id=user.id,
                language=lang,
            )
            await session.commit()
        await message.answer(
            format_detection_result(result, loc),
            parse_mode="HTML",
        )
    except RateLimitExceeded as exc:
        loc = await locale_for_chat(svc, message)
        await reply_error_message(message, loc, "error.limit.rate", retry=exc.retry_after)
    except KazakhMlApiUnavailableError:
        loc = await locale_for_chat(svc, message)
        await reply_error_message(message, loc, "error.external.ml_unavailable")
    except ValueError as exc:
        loc = await locale_for_chat(svc, message)
        key, kw = i18n_key_for_exception(exc)
        await reply_error_message(message, loc, key, **kw)
    except RuntimeError:
        loc = await locale_for_chat(svc, message)
        await reply_error_message(message, loc, "error.system.generic")
    except Exception as exc:
        logger.error("telegram_photo_error", error=str(exc), exc_info=True)
        loc = await locale_for_chat(svc, message)
        await reply_error_message(message, loc, "error.system.generic")
