"""
Telegram Bot Service — transport layer only.

Responsibilities:
  - Register aiogram handlers (routing).
  - Download files from Telegram (infrastructure detail of this transport).
  - Format reply messages.
  - Delegate ALL business logic to TelegramDetectionService and AuthRepository.

What this class must NOT do:
  - Create database sessions.
  - Call GeminiTextExtractor or AIDetectionModelService directly.
  - Contain any detection / limit logic.
  - Know about SQLAlchemy.

Dependencies are injected via __init__, making this class fully testable
without a running Telegram connection.
"""

from __future__ import annotations

import asyncio
import os
from typing import Protocol, runtime_checkable

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Document, Message, PhotoSize

from src.core.config import config
from src.core.gemini_config import gemini_config
from src.core.logging import get_logger
from src.dtos.ai_detection_dto import DetectionResult
from src.services.telegram_detection_service import (
    TelegramDetectionResult,
    TelegramDetectionService,
)

logger = get_logger(__name__)

# ── Formatting helpers ────────────────────────────────────────────────────────

SUPPORTED_EXTENSIONS: frozenset[str] = frozenset(gemini_config.ALLOWED_FILE_EXTENSIONS)

_RESULT_EMOJI = {
    DetectionResult.AI_GENERATED: "🤖",
    DetectionResult.HUMAN_WRITTEN: "✍️",
    DetectionResult.UNCERTAIN: "🤔",
}
_RESULT_LABEL = {
    DetectionResult.AI_GENERATED: "Сгенерировано ИИ",
    DetectionResult.HUMAN_WRITTEN: "Написано человеком",
    DetectionResult.UNCERTAIN: "Неопределённо",
}


def _confidence_bar(confidence: float, width: int = 10) -> str:
    filled = round(confidence * width)
    return "█" * filled + "░" * (width - filled)


def _render_result(r: TelegramDetectionResult) -> str:
    """Turn a TelegramDetectionResult into a Markdown message string."""
    emoji = _RESULT_EMOJI[r.result]
    label = _RESULT_LABEL[r.result]
    bar = _confidence_bar(r.confidence)
    pct = round(r.confidence * 100)

    lines = [
        f"{emoji} *Результат:* {label}",
        f"📊 *Уверенность:* {bar} {pct}%",
        f"📄 *Источник:* {r.source_label}",
    ]
    if r.file_name:
        lines.append(f"📁 *Файл:* `{r.file_name}`")

    lines.append(
        f"⏱ *Время:* {r.processing_time_ms} мс  |  📝 *Слов:* {r.word_count}"
    )
    lines.append(
        f"📈 *Осталось сегодня:* {r.daily_remaining}  |  "
        f"*в месяц:* {r.monthly_remaining}"
    )
    return "\n".join(lines)


# ── Session factory protocol ──────────────────────────────────────────────────
# TelegramBotService needs to open a fresh DB session per request so that
# TelegramDetectionService (and the repositories it uses) receive a properly
# scoped session.  We express this dependency as a Protocol so the bot stays
# decoupled from SQLAlchemy's concrete types.

@runtime_checkable
class SessionFactory(Protocol):
    """Async context manager that yields an AsyncSession."""

    def __call__(self):
        ...  # returns an async context manager


# ── Bot service ───────────────────────────────────────────────────────────────

class TelegramBotService:
    """
    Transport layer for the Telegram bot.

    Parameters
    ----------
    session_factory:
        Callable that returns an async context manager yielding an AsyncSession.
        Used to create a fresh unit-of-work per incoming message.
    detection_service_factory:
        Callable(session) -> TelegramDetectionService.
        Called with the per-request session so the service graph shares one
        transaction.
    auth_repository_factory:
        Callable(session) -> AuthRepository.
        Same reason — one session per request.
    """

    def __init__(
        self,
        session_factory,
        detection_service_factory,
        auth_repository_factory,
    ) -> None:
        if not config.TELEGRAM_BOT_TOKEN:
            logger.warning("telegram_bot_not_configured")
            self.bot: Bot | None = None
            self.dp: Dispatcher | None = None
            self._session_factory = None
            self._detection_service_factory = None
            self._auth_repository_factory = None
            return

        self.bot = Bot(token=config.TELEGRAM_BOT_TOKEN)
        self.dp = Dispatcher()
        self._session_factory = session_factory
        self._detection_service_factory = detection_service_factory
        self._auth_repository_factory = auth_repository_factory

        self._register_handlers()

    # ── Handler helpers ───────────────────────────────────────────────────────

    async def _download_bytes(self, file_id: str) -> bytes:
        """Download a Telegram file and return raw bytes."""
        tg_file = await self.bot.get_file(file_id)
        raw = await self.bot.download_file(tg_file.file_path)
        return raw.read() if hasattr(raw, "read") else bytes(raw)

    # ── Handler registration ──────────────────────────────────────────────────

    def _register_handlers(self) -> None:  # noqa: C901
        if not self.dp:
            return

        # ── /start ────────────────────────────────────────────────────────────
        @self.dp.message(Command("start"))
        async def handle_start(message: Message) -> None:
            parts = (message.text or "").split(maxsplit=1)

            if len(parts) < 2:
                await message.answer(
                    "Добро пожаловать!\n\n"
                    "Чтобы подключить аккаунт, воспользуйтесь ссылкой "
                    "из настроек профиля на сайте."
                )
                return

            token = parts[1].strip()
            chat_id = str(message.chat.id)

            try:
                async with self._session_factory() as session:
                    repo = self._auth_repository_factory(session)
                    user = await repo.get_user_by_telegram_token(token)

                    if not user:
                        await message.answer(
                            "❌ Ссылка недействительна или истёк срок действия.\n"
                            "Сгенерируйте новую ссылку в настройках профиля."
                        )
                        logger.warning(
                            "telegram_invalid_token",
                            chat_id=chat_id,
                            token_prefix=token[:8],
                        )
                        return

                    existing = await repo.get_user_by_telegram_chat_id(chat_id)
                    if existing:
                        if existing.id == user.id:
                            await message.answer(
                                "✅ Аккаунт уже подключён!\n\n"
                                "Отправьте текст или файл для проверки на ИИ."
                            )
                        else:
                            await message.answer(
                                "⚠️ Этот Telegram-аккаунт привязан к другому пользователю."
                            )
                        return

                    await repo.connect_telegram_account(user.id, chat_id)
                    await session.commit()

                    supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
                    await message.answer(
                        "✅ Аккаунт успешно подключён!\n\n"
                        "Теперь отправьте мне:\n"
                        "• 📝 Текст — проверю на ИИ\n"
                        "• 📎 Файл — PDF, DOCX, TXT, PPTX, HTML…\n"
                        "• 🖼 Изображение с текстом\n\n"
                        f"Поддерживаемые форматы: {supported}"
                    )
                    logger.info(
                        "telegram_account_connected",
                        user_id=user.id,
                        chat_id=chat_id,
                    )

            except Exception as exc:
                logger.error("telegram_start_error", error=str(exc), exc_info=True)
                await message.answer("❌ Ошибка при подключении. Попробуйте позже.")

        # ── /help ─────────────────────────────────────────────────────────────
        @self.dp.message(Command("help"))
        async def handle_help(message: Message) -> None:
            await message.answer(
                "ℹ️ *Помощь*\n\n"
                "Отправьте:\n"
                "• 📝 *Текст* — мин. 50 символов\n"
                "• 📎 *Файл* — PDF, DOCX, TXT, PPTX, HTML…\n"
                "• 🖼 *Изображение* с текстом\n\n"
                "*Команды:*\n"
                "/start — подключить аккаунт\n"
                "/help — эта справка\n"
                "/disconnect — отвязать аккаунт\n\n"
                f"Макс. размер файла: {gemini_config.MAX_FILE_SIZE_MB} МБ",
                parse_mode="Markdown",
            )

        # ── /disconnect ───────────────────────────────────────────────────────
        @self.dp.message(Command("disconnect"))
        async def handle_disconnect(message: Message) -> None:
            chat_id = str(message.chat.id)
            try:
                async with self._session_factory() as session:
                    repo = self._auth_repository_factory(session)
                    user = await repo.get_user_by_telegram_chat_id(chat_id)
                    if not user:
                        await message.answer("Аккаунт не подключён к этому чату.")
                        return
                    await repo.disconnect_telegram(user.id)
                    await session.commit()
                    await message.answer("✅ Аккаунт отключён.")
                    logger.info(
                        "telegram_disconnected_via_bot",
                        user_id=user.id,
                        chat_id=chat_id,
                    )
            except Exception as exc:
                logger.error("telegram_disconnect_error", error=str(exc), exc_info=True)
                await message.answer("❌ Ошибка. Попробуйте позже.")

        # ── Plain text ────────────────────────────────────────────────────────
        @self.dp.message(F.text & ~F.text.startswith("/"))
        async def handle_text(message: Message) -> None:
            chat_id = str(message.chat.id)
            text = (message.text or "").strip()

            if len(text) < 50:
                await message.answer(
                    f"⚠️ Текст слишком короткий ({len(text)} симв.).\n"
                    "Минимум — 50 символов."
                )
                return

            try:
                async with self._session_factory() as session:
                    repo = self._auth_repository_factory(session)
                    user = await repo.get_user_by_telegram_chat_id(chat_id)

                    if not user:
                        await message.answer(
                            "⚠️ Аккаунт не привязан.\n"
                            "Используйте ссылку из профиля на сайте."
                        )
                        return

                    await message.bot.send_chat_action(
                        chat_id=message.chat.id, action="typing"
                    )

                    svc = self._detection_service_factory(session)
                    result = await svc.detect_text(text=text, user_id=user.id)
                    await session.commit()

                await message.answer(_render_result(result), parse_mode="Markdown")
                logger.info(
                    "telegram_text_done",
                    user_id=user.id,
                    result=result.result.value,
                )

            except ValueError as exc:
                await message.answer(f"⚠️ {exc}")
            except Exception as exc:
                logger.error("telegram_text_error", error=str(exc), exc_info=True)
                await message.answer("❌ Ошибка при анализе текста. Попробуйте позже.")

        # ── Document ──────────────────────────────────────────────────────────
        @self.dp.message(F.document)
        async def handle_document(message: Message) -> None:
            chat_id = str(message.chat.id)
            doc: Document = message.document
            file_name = doc.file_name or "document"
            ext = os.path.splitext(file_name)[1].lower()

            if ext not in SUPPORTED_EXTENSIONS:
                await message.answer(
                    f"⚠️ Формат *{ext or 'неизвестный'}* не поддерживается.\n"
                    f"Поддерживаемые: `{', '.join(sorted(SUPPORTED_EXTENSIONS))}`",
                    parse_mode="Markdown",
                )
                return

            max_bytes = gemini_config.MAX_FILE_SIZE_MB * 1024 * 1024
            if doc.file_size and doc.file_size > max_bytes:
                await message.answer(
                    f"⚠️ Файл слишком большой "
                    f"({doc.file_size / 1024 / 1024:.1f} МБ).\n"
                    f"Максимум: {gemini_config.MAX_FILE_SIZE_MB} МБ."
                )
                return

            try:
                async with self._session_factory() as session:
                    repo = self._auth_repository_factory(session)
                    user = await repo.get_user_by_telegram_chat_id(chat_id)

                    if not user:
                        await message.answer(
                            "⚠️ Аккаунт не привязан.\n"
                            "Используйте ссылку из профиля на сайте."
                        )
                        return

                    await message.bot.send_chat_action(
                        chat_id=message.chat.id, action="upload_document"
                    )

                    # Infrastructure: download bytes (transport concern)
                    file_bytes = await self._download_bytes(doc.file_id)
                    content_type = doc.mime_type or "application/octet-stream"

                    svc = self._detection_service_factory(session)
                    result = await svc.detect_file(
                        file_bytes=file_bytes,
                        file_name=file_name,
                        content_type=content_type,
                        user_id=user.id,
                    )
                    await session.commit()

                await message.answer(_render_result(result), parse_mode="Markdown")
                logger.info(
                    "telegram_file_done",
                    user_id=user.id,
                    file_name=file_name,
                    result=result.result.value,
                )

            except ValueError as exc:
                await message.answer(f"⚠️ {exc}")
            except RuntimeError:
                await message.answer(
                    "❌ Не удалось извлечь текст из файла.\n"
                    "Убедитесь, что файл содержит читаемый текст."
                )
            except Exception as exc:
                logger.error(
                    "telegram_file_error",
                    file_name=file_name,
                    error=str(exc),
                    exc_info=True,
                )
                await message.answer("❌ Ошибка при анализе файла. Попробуйте позже.")

        # ── Photo ─────────────────────────────────────────────────────────────
        @self.dp.message(F.photo)
        async def handle_photo(message: Message) -> None:
            chat_id = str(message.chat.id)
            photo: PhotoSize = message.photo[-1]

            try:
                async with self._session_factory() as session:
                    repo = self._auth_repository_factory(session)
                    user = await repo.get_user_by_telegram_chat_id(chat_id)

                    if not user:
                        await message.answer(
                            "⚠️ Аккаунт не привязан.\n"
                            "Используйте ссылку из профиля на сайте."
                        )
                        return

                    await message.bot.send_chat_action(
                        chat_id=message.chat.id, action="upload_photo"
                    )

                    file_bytes = await self._download_bytes(photo.file_id)
                    file_name = f"photo_{photo.file_unique_id}.jpg"

                    svc = self._detection_service_factory(session)
                    result = await svc.detect_image(
                        image_bytes=file_bytes,
                        file_name=file_name,
                        user_id=user.id,
                    )
                    await session.commit()

                await message.answer(_render_result(result), parse_mode="Markdown")
                logger.info(
                    "telegram_photo_done",
                    user_id=user.id,
                    result=result.result.value,
                )

            except ValueError as exc:
                await message.answer(f"⚠️ {exc}")
            except RuntimeError:
                await message.answer(
                    "❌ Не удалось извлечь текст из изображения.\n"
                    "Убедитесь, что на фото есть читаемый текст."
                )
            except Exception as exc:
                logger.error("telegram_photo_error", error=str(exc), exc_info=True)
                await message.answer(
                    "❌ Ошибка при анализе изображения. Попробуйте позже."
                )

        # ── Catch-all ─────────────────────────────────────────────────────────
        @self.dp.message()
        async def handle_unknown(message: Message) -> None:
            await message.answer(
                "❓ Не понимаю этот тип сообщения.\n\n"
                "Отправьте:\n"
                "• 📝 Текст\n"
                "• 📎 Файл (PDF, DOCX, TXT…)\n"
                "• 🖼 Изображение с текстом\n\n"
                "Или /help для справки."
            )

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def start(self) -> None:
        if not self.bot or not self.dp:
            logger.warning("telegram_bot_not_started_not_configured")
            return
        logger.info("telegram_bot_starting")
        try:
            await self.dp.start_polling(self.bot, skip_updates=True)
        except asyncio.CancelledError:
            logger.info("telegram_bot_polling_cancelled")
        except Exception as exc:
            logger.error(
                "telegram_bot_start_error",
                error=str(exc),
                exc_info=True,
            )

    async def stop(self) -> None:
        if not self.bot:
            return
        logger.info("telegram_bot_stopping")
        try:
            await self.bot.session.close()
        except Exception as exc:
            logger.error("telegram_bot_stop_error", error=str(exc), exc_info=True)

    async def send_message(self, chat_id: str, text: str) -> bool:
        """Utility helper — send a plain message to a chat."""
        if not self.bot:
            return False
        try:
            await self.bot.send_message(chat_id=int(chat_id), text=text)
            return True
        except Exception as exc:
            logger.error(
                "telegram_send_failed",
                chat_id=chat_id,
                error=str(exc),
                exc_info=True,
            )
            return False