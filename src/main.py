"""
Main FastAPI application - HTTP API only.

For the Telegram bot, see src/bot_main.py
"""

import asyncio
from contextlib import asynccontextmanager

from dishka import make_async_container
from dishka.integrations.fastapi import DishkaRoute, FromDishka
from dishka.integrations import fastapi as fastapi_integration
from fastapi import APIRouter, FastAPI, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncEngine

from src.api.v1.auth import router as auth_router
from src.api.v1.ai_detection import router as ai_detection_router
from src.api.v1.limits import router as limits_router
from src.api.v1.telegram import router as telegram_router
from src.core.config import config, Config
from src.core.logging import get_logger, setup_logging
from src.db.database import check_db_connection
from src.ioc import AppProvider

setup_logging(
    level="DEBUG" if config.DEBUG else "INFO",
    json_logs=not config.DEBUG,
)

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI application lifecycle - HTTP API only."""
    logger.info("application_startup", app_name=config.APP_NAME)

    try:
        container = app.state.dishka_container
        engine = await container.get(AsyncEngine)

        if not await check_db_connection(engine):
            raise RuntimeError("Database connection failed at startup")

        logger.info("startup_database_connected")

    except Exception as exc:
        logger.error(
            "startup_failed",
            error=str(exc),
            error_type=type(exc).__name__,
            exc_info=True,
        )
        raise

    yield

    logger.info("application_shutdown", app_name=config.APP_NAME)


def create_app() -> FastAPI:
    """Create FastAPI application."""
    container = make_async_container(AppProvider(), context={Config: config})

    app = FastAPI(
        title=config.APP_NAME,
        description="FastAPI application - AI Detection API",
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