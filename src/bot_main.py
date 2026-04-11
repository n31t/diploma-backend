"""
Telegram Bot Entry Point

Runs as a separate process from the FastAPI application.
Shares the same domain logic, services, and database.
"""

import asyncio

from dishka import make_async_container
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from src.core.config import config, Config
from src.core.logging import get_logger, setup_logging
from src.db.database import check_db_connection
from src.infrastructure.redis_client import RedisClient, create_redis_client
from src.ioc import AppProvider
from src.services.gemini_service import GeminiTextExtractor
from src.services.ml_model_service import AIDetectionModelService
from src.services.newspaper_service import NewspaperService
from src.services.telegram_bot_service import TelegramBotService
from src.services.text_normalization_service import TextNormalizationService

setup_logging(
    level="DEBUG" if config.DEBUG else "INFO",
    json_logs=not config.DEBUG,
)

logger = get_logger(__name__)


async def main():
    """Main entry point for the Telegram bot."""
    logger.info("telegram_bot_starting", app_name=config.APP_NAME)

    container = make_async_container(AppProvider(), context={Config: config})
    redis_connection: Redis | None = None

    try:
        engine = await container.get(AsyncEngine)
        if not await check_db_connection(engine):
            raise RuntimeError("Database connection failed at startup")
        logger.info("bot_database_connected")

        session_maker = await container.get(async_sessionmaker[AsyncSession])
        gemini_svc = await container.get(GeminiTextExtractor)
        ml_svc = await container.get(AIDetectionModelService)
        norm_svc = await container.get(TextNormalizationService)
        newspaper_svc = await container.get(NewspaperService)

        redis_connection = await create_redis_client()
        redis_client: RedisClient | None = RedisClient(redis_connection)

        telegram_bot = TelegramBotService(
            session_factory=session_maker,
            app_config=config,
            gemini_service=gemini_svc,
            ml_model_service=ml_svc,
            normalization_service=norm_svc,
            newspaper_service=newspaper_svc,
            redis_client=redis_client,
        )

        if not telegram_bot.bot:
            logger.error("telegram_bot_not_configured")
            raise RuntimeError("TELEGRAM_BOT_TOKEN not set in environment")

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
        if redis_connection is not None:
            try:
                await redis_connection.close()
            except Exception as exc:
                logger.warning("redis_close_error", error=str(exc))
        logger.info("telegram_bot_shutdown")


if __name__ == "__main__":
    asyncio.run(main())
