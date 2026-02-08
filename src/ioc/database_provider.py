"""
Database provider for dependency injection.

This module provides database-related dependencies including:
- AsyncEngine (singleton)
- SessionMaker (singleton)
- AsyncSession (per-request)
"""

from typing import AsyncIterable

from dishka import Provider, Scope, from_context, provide
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, AsyncEngine, create_async_engine

from src.core.config import Config


class DatabaseProvider(Provider):
    """
    Provider for database-related dependencies.

    Manages:
    - APP scope: Engine and SessionMaker (singletons)
    - REQUEST scope: AsyncSession
    """

    # Config injected from application context at startup
    config = from_context(provides=Config, scope=Scope.APP)

    @provide(scope=Scope.APP)
    def get_engine(self, config: Config) -> AsyncEngine:
        """
        Create and provide SQLAlchemy async engine.

        Args:
            config: Application configuration

        Returns:
            AsyncEngine configured with connection pooling
        """
        return create_async_engine(
            config.db_url,
            echo=False,
            pool_pre_ping=True,
            pool_recycle=3600,
            pool_timeout=20,
            max_overflow=0,
        )

    @provide(scope=Scope.APP)
    def get_session_maker(self, engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
        """
        Create and provide session maker factory.

        Args:
            engine: SQLAlchemy async engine

        Returns:
            async_sessionmaker configured for the application
        """
        return async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )

    @provide(scope=Scope.REQUEST)
    async def get_session(
        self, session_maker: async_sessionmaker[AsyncSession]
    ) -> AsyncIterable[AsyncSession]:
        """
        Provide database session for the current request.

        Uses async context manager to ensure proper cleanup.
        Automatically commits on success, rolls back on error.

        Args:
            session_maker: Session factory

        Yields:
            AsyncSession for the current request
        """
        async with session_maker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()
