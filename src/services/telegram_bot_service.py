"""
Telegram Bot service — handles the /start deep-link flow that binds a
Telegram chat to a platform user account.

The bot runs as an independent asyncio task (long-polling via aiogram).
It creates its own SQLAlchemy session maker so it stays outside the
Dishka request-scope used by the FastAPI application.
"""

import asyncio

from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.core.config import config
from src.core.logging import get_logger
from src.repositories.auth_repository import AuthRepository

logger = get_logger(__name__)


class TelegramBotService:
    """Encapsulates the aiogram Bot + Dispatcher lifecycle."""

    def __init__(self) -> None:
        if not config.TELEGRAM_BOT_TOKEN:
            logger.warning("telegram_bot_not_configured")
            self.bot: Bot | None = None
            self.dp: Dispatcher | None = None
            self._session_maker: async_sessionmaker | None = None
            return

        self.bot = Bot(token=config.TELEGRAM_BOT_TOKEN)
        self.dp = Dispatcher()

        engine = create_async_engine(
            config.db_url,
            echo=False,
            pool_pre_ping=True,
            pool_recycle=3600,
        )
        self._session_maker = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        self._register_handlers()

    # ── Handler registration ────────────────────────────────────────────────

    def _register_handlers(self) -> None:
        if not self.dp:
            return

        @self.dp.message(Command("start"))
        async def handle_start(message: Message) -> None:
            """
            /start <token>

            The frontend generates a deep-link like
            ``https://t.me/<bot>?start=<token>`` that Telegram passes to the
            bot as ``/start <token>``.  We look up the token in the DB,
            validate it, then bind the chat_id to the user.
            """
            parts = message.text.split(maxsplit=1) if message.text else []

            if len(parts) < 2:
                await message.answer(
                    "Добро пожаловать!\n\n"
                    "Чтобы подключить аккаунт, воспользуйтесь ссылкой из "
                    "настроек профиля на сайте."
                )
                return

            token = parts[1].strip()

            try:
                async with self._session_maker() as session:
                    repo = AuthRepository(session)

                    user = await repo.get_user_by_telegram_token(token)
                    if not user:
                        await message.answer(
                            "Ссылка недействительна или истёк срок её действия.\n"
                            "Пожалуйста, сгенерируйте новую ссылку в настройках профиля."
                        )
                        logger.warning(
                            "telegram_connection_invalid_token",
                            chat_id=message.chat.id,
                            token_prefix=token[:8],
                        )
                        return

                    chat_id = str(message.chat.id)
                    existing = await repo.get_user_by_telegram_chat_id(chat_id)

                    if existing:
                        if existing.id == user.id:
                            await message.answer("Ваш аккаунт уже подключён к этому чату!")
                            logger.info(
                                "telegram_already_connected",
                                user_id=user.id,
                                chat_id=chat_id,
                            )
                        else:
                            await message.answer(
                                "Этот Telegram-аккаунт уже привязан к другому пользователю.\n"
                                "Пожалуйста, используйте другой Telegram-аккаунт."
                            )
                            logger.warning(
                                "telegram_chat_already_used",
                                existing_user_id=existing.id,
                                new_user_id=user.id,
                                chat_id=chat_id,
                            )
                        return

                    await repo.connect_telegram_account(user.id, chat_id)
                    await session.commit()

                    await message.answer(
                        "✅ Аккаунт успешно подключён!\n"
                        "Теперь вы можете проверять тексты и файлы, для этого скиньте ваш текст или файл в этот чат."
                    )
                    logger.info(
                        "telegram_account_connected",
                        user_id=user.id,
                        chat_id=chat_id,
                        username=user.username,
                    )

            except Exception as exc:
                logger.error(
                    "telegram_connection_error",
                    chat_id=message.chat.id,
                    error=str(exc),
                    error_type=type(exc).__name__,
                    exc_info=True,
                )
                await message.answer(
                    "Произошла ошибка при подключении аккаунта.\n"
                    "Пожалуйста, попробуйте позже."
                )

        @self.dp.message(Command("help"))
        async def handle_help(message: Message) -> None:
            await message.answer(
                "ℹ️ *Помощь*\n\n"
                "Используйте ссылку из настроек профиля на сайте, чтобы "
                "привязать этот Telegram-чат к вашему аккаунту.\n\n"
                "*Команды:*\n"
                "/start — подключить аккаунт\n"
                "/help — это сообщение",
                parse_mode="Markdown",
            )

        @self.dp.message(Command("disconnect"))
        async def handle_disconnect(message: Message) -> None:
            """Allow users to unlink their account directly from Telegram."""
            chat_id = str(message.chat.id)
            try:
                async with self._session_maker() as session:
                    repo = AuthRepository(session)
                    user = await repo.get_user_by_telegram_chat_id(chat_id)
                    if not user:
                        await message.answer("Аккаунт не подключён к этому чату.")
                        return
                    await repo.disconnect_telegram(user.id)
                    await session.commit()
                    await message.answer("Аккаунт отключён.")
                    logger.info("telegram_disconnected_via_bot", user_id=user.id, chat_id=chat_id)
            except Exception as exc:
                logger.error(
                    "telegram_disconnect_error",
                    chat_id=chat_id,
                    error=str(exc),
                    exc_info=True,
                )
                await message.answer("Произошла ошибка. Пожалуйста, попробуйте позже.")

    # ── Lifecycle ───────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Start long-polling. Blocks until cancelled."""
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
                error_type=type(exc).__name__,
                exc_info=True,
            )

    async def stop(self) -> None:
        """Gracefully close the bot session."""
        if not self.bot:
            return
        logger.info("telegram_bot_stopping")
        try:
            await self.bot.session.close()
        except Exception as exc:
            logger.error(
                "telegram_bot_stop_error",
                error=str(exc),
                error_type=type(exc).__name__,
                exc_info=True,
            )

    async def send_message(self, chat_id: str, text: str) -> bool:
        """
        Utility helper — send *text* to *chat_id*.

        Returns ``True`` on success, ``False`` otherwise (so callers don't
        have to handle Telegram errors themselves).
        """
        if not self.bot:
            logger.warning("telegram_send_skipped_not_configured", chat_id=chat_id)
            return False
        try:
            await self.bot.send_message(chat_id=int(chat_id), text=text)
            return True
        except Exception as exc:
            logger.error(
                "telegram_send_message_failed",
                chat_id=chat_id,
                error=str(exc),
                exc_info=True,
            )
            return False


# Module-level singleton — imported by main.py for lifespan management
telegram_bot_service = TelegramBotService()