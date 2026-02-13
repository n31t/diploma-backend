"""
Telegram Bot Entry Point

Runs as a separate process from the FastAPI application.
Shares the same domain logic, services, and database.
"""

import asyncio
from contextlib import asynccontextmanager

from dishka import make_async_container
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from src.core.config import config, Config
from src.core.logging import get_logger, setup_logging
from src.db.database import check_db_connection
from src.ioc import AppProvider
from src.repositories.auth_repository import AuthRepository
from src.repositories.ai_detection_repository import AIDetectionRepository
from src.services.gemini_service import GeminiTextExtractor
from src.services.ml_model_service import AIDetectionModelService
from src.services.ai_detection_service import AIDetectionService
from src.services.telegram_detection_service import TelegramDetectionService
from src.services.telegram_bot_service import TelegramBotService

setup_logging(
    level="DEBUG" if config.DEBUG else "INFO",
    json_logs=not config.DEBUG,
)

logger = get_logger(__name__)


def _build_telegram_bot_service(
        session_maker: async_sessionmaker[AsyncSession],
        gemini_service: GeminiTextExtractor,
        ml_model_service: AIDetectionModelService,
) -> TelegramBotService:
    """
    Wire TelegramBotService with factory callables.

    Each Telegram message gets its own unit-of-work (session + services).
    This is the same pattern used in FastAPI requests, just applied to
    Telegram messages instead.
    """

    def detection_service_factory(session: AsyncSession) -> TelegramDetectionService:
        ai_detection_repo = AIDetectionRepository(session)
        ai_detection_svc = AIDetectionService(
            gemini_service,
            ml_model_service,
            ai_detection_repo,
        )
        return TelegramDetectionService(ai_detection_svc)

    def auth_repository_factory(session: AsyncSession) -> AuthRepository:
        return AuthRepository(session)

    return TelegramBotService(
        session_factory=session_maker,
        detection_service_factory=detection_service_factory,
        auth_repository_factory=auth_repository_factory,
    )


async def main():
    """Main entry point for the Telegram bot."""
    logger.info("telegram_bot_starting", app_name=config.APP_NAME)

    # Create Dishka container with same providers as FastAPI
    container = make_async_container(AppProvider(), context={Config: config})

    try:
        # Get APP-scoped dependencies (singletons)
        engine = await container.get(AsyncEngine)
        if not await check_db_connection(engine):
            raise RuntimeError("Database connection failed at startup")
        logger.info("bot_database_connected")

        session_maker = await container.get(async_sessionmaker[AsyncSession])
        gemini_svc = await container.get(GeminiTextExtractor)
        ml_svc = await container.get(AIDetectionModelService)

        # Build bot with factory pattern
        telegram_bot = _build_telegram_bot_service(session_maker, gemini_svc, ml_svc)

        if not telegram_bot.bot:
            logger.error("telegram_bot_not_configured")
            raise RuntimeError("TELEGRAM_BOT_TOKEN not set in environment")

        # Start bot (blocking call)
        logger.info("telegram_bot_ready")
        await telegram_bot.start()

    except KeyboardInterrupt:
        logger.info("telegram_bot_interrupted_by_user")
    except Exception as exc:
        logger.error(
            "telegram_bot_failed",
            error=str(exc),
            error_type=type(exc).__name__,
            exc_info=True,
        )
        raise
    finally:
        await container.close()
        logger.info("telegram_bot_shutdown")


if __name__ == "__main__":
    asyncio.run(main())