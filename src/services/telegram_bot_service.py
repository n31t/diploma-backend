"""
Telegram Bot Service — aiogram transport: commands, menus, i18n.

Delegates detection and billing to existing domain services.
"""

from __future__ import annotations

import asyncio

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from src.core.config import Config
from src.core.logging import get_logger
from src.infrastructure.redis_client import RedisClient
from src.repositories.ai_detection_repository import AIDetectionRepository
from src.repositories.auth_repository import AuthRepository
from src.repositories.rate_limiter_repository import RateLimiterRepository
from src.repositories.subscription_repository import SubscriptionRepository
from src.services.ai_detection_service import AIDetectionService
from src.services.gemini_service import GeminiTextExtractor
from src.services.ml_model_service import AIDetectionModelService
from src.services.newspaper_service import NewspaperService
from src.services.rate_limiter_service import RateLimiterService
from src.services.stripe_service import StripeService
from src.services.telegram_detection_service import TelegramDetectionService
from src.services.text_normalization_service import TextNormalizationService
from src.services.url_detection_service import URLDetectionService
from src.telegram_bot.context import TelegramSessionContext
from src.telegram_bot.routers import register_telegram_routers

logger = get_logger(__name__)


class TelegramBotService:
    """Transport layer for the Telegram bot."""

    def __init__(
        self,
        session_factory,
        *,
        app_config: Config,
        gemini_service: GeminiTextExtractor,
        ml_model_service: AIDetectionModelService,
        normalization_service: TextNormalizationService,
        newspaper_service: NewspaperService,
        redis_client: RedisClient | None,
    ) -> None:
        if not app_config.TELEGRAM_BOT_TOKEN:
            logger.warning("telegram_bot_not_configured")
            self.bot: Bot | None = None
            self.dp: Dispatcher | None = None
            self._session_factory = None
            self._redis = None
            return

        self.bot = Bot(token=app_config.TELEGRAM_BOT_TOKEN)
        self.dp = Dispatcher(storage=MemoryStorage())
        self._session_factory = session_factory
        self._config = app_config
        self._gemini = gemini_service
        self._ml = ml_model_service
        self._norm = normalization_service
        self._newspaper = newspaper_service
        self._redis = redis_client

        register_telegram_routers(self.dp, self)

    def _build_ctx(self, session) -> TelegramSessionContext:
        auth = AuthRepository(session)
        ai_repo = AIDetectionRepository(session)
        sub_repo = SubscriptionRepository(session)
        ai_det = AIDetectionService(
            self._gemini, self._ml, ai_repo, self._norm
        )
        url_det = URLDetectionService(
            self._newspaper, self._ml, ai_repo, self._norm
        )
        tg_det = TelegramDetectionService(ai_det, url_det)
        stripe = StripeService(
            self._config, sub_repo, ai_repo, auth
        )
        rate: RateLimiterService | None = None
        if self._redis is not None:
            rate = RateLimiterService(RateLimiterRepository(self._redis))
        return TelegramSessionContext(
            auth=auth,
            ai_repo=ai_repo,
            sub_repo=sub_repo,
            ai_detection=ai_det,
            telegram_detection=tg_det,
            stripe=stripe,
            rate_limiter=rate,
        )

    async def _rate_check(self, ctx: TelegramSessionContext, user_id: str) -> None:
        if not ctx.rate_limiter:
            return
        await ctx.rate_limiter.check_and_increment(user_id)

    async def _download_bytes(self, file_id: str) -> bytes:
        assert self.bot
        tg_file = await self.bot.get_file(file_id)
        raw = await self.bot.download_file(tg_file.file_path)
        return raw.read() if hasattr(raw, "read") else bytes(raw)

    async def start(self) -> None:
        if not self.bot or not self.dp:
            logger.warning("telegram_bot_not_started_not_configured")
            return
        logger.info("telegram_bot_starting")
        try:
            await self.bot.delete_webhook(drop_pending_updates=True)
            logger.info("telegram_webhook_cleared_for_polling")
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
