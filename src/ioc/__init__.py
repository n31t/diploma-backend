"""
Dependency injection container configuration using Dishka.
"""

from src.ioc.database_provider import DatabaseProvider
from src.ioc.redis_provider import RedisProvider
from src.ioc.repository_provider import RepositoryProvider
from src.ioc.service_provider import ServiceProvider


class AppProvider(
    DatabaseProvider,
    RepositoryProvider,
    ServiceProvider,
    RedisProvider,
):
    """
    Main dependency injection provider for the application.

    Combines all provider modules:
    - DatabaseProvider: Engine, SessionMaker, AsyncSession
    - RepositoryProvider: All repository instances
    - ServiceProvider: All service instances
    """
    pass


__all__ = ["AppProvider"]
