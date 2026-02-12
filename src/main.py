"""
Main FastAPI application with logging, monitoring, and middleware setup.
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
from src.services.telegram_bot_service import telegram_bot_service

setup_logging(
    level="DEBUG" if config.DEBUG else "INFO",
    json_logs=not config.DEBUG,
)

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.

    Handles startup and shutdown events, including database connection verification.
    """
    logger.info("application_startup", app_name=config.APP_NAME)

    # Verify database connection at startup
    try:
        async with app.state.dishka_container() as request_container:
            engine = await request_container.get(AsyncEngine)
            is_connected = await check_db_connection(engine)

            if not is_connected:
                logger.error("startup_failed_database_unreachable")
                raise RuntimeError("Database connection failed at startup")

            logger.info("startup_database_connected")
    except Exception as e:
        logger.error(
            "startup_failed",
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True,
        )
        raise

    # Start the Telegram bot in a background task (non-blocking)
    bot_task = None
    if telegram_bot_service.bot:
        bot_task = asyncio.create_task(telegram_bot_service.start())
        logger.info("telegram_bot_task_created")
    else:
        logger.info("telegram_bot_skipped_not_configured")

    yield

    # Shutdown
    if bot_task and not bot_task.done():
        bot_task.cancel()
        try:
            await bot_task
        except asyncio.CancelledError:
            pass

    await telegram_bot_service.stop()
    logger.info("application_shutdown", app_name=config.APP_NAME)


def create_app() -> FastAPI:
    """
    Create and configure FastAPI application with Dishka DI container.

    Returns:
        Configured FastAPI application instance
    """
    # Create Dishka container with AppProvider and inject config context
    container = make_async_container(AppProvider(), context={Config: config})

    # Create FastAPI app
    app = FastAPI(
        title=config.APP_NAME,
        description="FastAPI application with structured logging and monitoring",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Setup Dishka integration with FastAPI
    fastapi_integration.setup_dishka(container, app)

    return app


app = create_app()


@app.get("/health", tags=["Health"])
async def health_check():
    """
    Basic liveness check endpoint.

    Returns 200 if the application is alive (but not necessarily ready).
    Used by Kubernetes liveness probes.
    """
    return {"status": "healthy", "service": config.APP_NAME}


# Create a router with DishkaRoute for dependency injection in health checks
health_router = APIRouter(route_class=DishkaRoute, tags=["Health"])


@health_router.get("/health/ready")
async def readiness_check(engine: FromDishka[AsyncEngine]):
    """
    Readiness check endpoint with database connectivity verification.

    Returns 200 if the service is ready to accept traffic.
    Checks database connectivity to ensure the service can handle requests.
    Used by Kubernetes readiness probes.

    Args:
        engine: SQLAlchemy async engine (injected by Dishka)

    Returns:
        dict: Status information including database connectivity

    Raises:
        HTTPException 503: If database is unreachable
    """
    is_db_connected = await check_db_connection(engine)

    if not is_db_connected:
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