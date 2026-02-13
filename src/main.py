"""
Main FastAPI application with logging, monitoring, and middleware setup.
"""

import asyncio
from contextlib import asynccontextmanager

from dishka import make_async_container
from dishka.integrations.fastapi import DishkaRoute, FromDishka
from dishka.integrations import fastapi as fastapi_integration
from fastapi import APIRouter, FastAPI, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from src.api.v1.auth import router as auth_router
from src.api.v1.ai_detection import router as ai_detection_router
from src.api.v1.limits import router as limits_router
from src.api.v1.telegram import router as telegram_router
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

    The bot runs outside FastAPI's request cycle (it's a long-polling loop),
    so it cannot use Dishka's request-scoped container directly.  Instead we
    pass factory functions that create a fresh unit-of-work (session +
    repositories + services) for every incoming Telegram message — which is
    exactly what a request scope means in this context.

    Factories receive the session as an argument so that all objects in the
    same message-handling call share one transaction.
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("application_startup", app_name=config.APP_NAME)

    try:
        container = app.state.dishka_container

        engine = await container.get(AsyncEngine)
        if not await check_db_connection(engine):
            raise RuntimeError("Database connection failed at startup")
        logger.info("startup_database_connected")

        # APP-scoped зависимости
        session_maker = await container.get(async_sessionmaker[AsyncSession])
        gemini_svc = await container.get(GeminiTextExtractor)
        ml_svc = await container.get(AIDetectionModelService)

    except Exception as exc:
        logger.error(
            "startup_failed",
            error=str(exc),
            error_type=type(exc).__name__,
            exc_info=True,
        )
        raise

    telegram_bot = _build_telegram_bot_service(session_maker, gemini_svc, ml_svc)
    app.state.telegram_bot = telegram_bot

    bot_task = None
    if telegram_bot.bot:
        bot_task = asyncio.create_task(telegram_bot.start())
        logger.info("telegram_bot_task_created")
    else:
        logger.info("telegram_bot_skipped_not_configured")

    yield

    if bot_task and not bot_task.done():
        bot_task.cancel()
        try:
            await bot_task
        except asyncio.CancelledError:
            pass

    await telegram_bot.stop()
    logger.info("application_shutdown", app_name=config.APP_NAME)



def create_app() -> FastAPI:
    container = make_async_container(AppProvider(), context={Config: config})

    app = FastAPI(
        title=config.APP_NAME,
        description="FastAPI application with structured logging and monitoring",
        version="0.1.0",
        lifespan=lifespan,
    )

    fastapi_integration.setup_dishka(container, app)
    return app


app = create_app()


@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "healthy", "service": config.APP_NAME}


health_router = APIRouter(route_class=DishkaRoute, tags=["Health"])


@health_router.get("/health/ready")
async def readiness_check(engine: FromDishka[AsyncEngine]):
    if not await check_db_connection(engine):
        logger.error("readiness_check_failed_database_unreachable")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection failed",
        )
    return {"status": "ready", "service": config.APP_NAME, "database": "connected"}


app.include_router(health_router)
app.include_router(auth_router, prefix="/api/v1", tags=["Authentication"])
app.include_router(ai_detection_router, prefix="/api/v1", tags=["AI Detection"])
app.include_router(limits_router, prefix="/api/v1", tags=["User Limits"])
app.include_router(telegram_router, prefix="/api/v1", tags=["Telegram"])