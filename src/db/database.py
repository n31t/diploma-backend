"""
Database configuration and utility functions.

This module provides utility functions for database operations.
All dependency injection is handled by Dishka in src/ioc.py.
The Base class is defined in src/models/base.py.
"""

from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy import text
import logging

logger = logging.getLogger(__name__)


async def check_db_connection(engine: AsyncEngine) -> bool:
    """
    Check if database connection is working.

    Args:
        engine: SQLAlchemy async engine

    Returns:
        True if connection successful, False otherwise
    """
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info("Database connection successful")
        return True
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        return False


async def close_db(engine: AsyncEngine) -> None:
    """
    Close database connections and dispose engine.

    Args:
        engine: SQLAlchemy async engine to dispose
    """
    await engine.dispose()
    logger.info("Database connections closed")
