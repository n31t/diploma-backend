"""
Redis provider for dependency injection.
"""

from typing import AsyncIterable

from dishka import Provider, Scope, provide
from redis.asyncio import Redis

from src.infrastructure.redis_client import RedisClient, create_redis_client
from src.repositories.rate_limiter_repository import RateLimiterRepository
from src.services.rate_limiter_service import RateLimiterService


class RedisProvider(Provider):
    """Provider for Redis-related dependencies."""

    @provide(scope=Scope.APP)
    async def get_redis_connection(self) -> AsyncIterable[Redis]:
        """
        Provide Redis connection (singleton).

        Yields:
            Redis connection instance
        """
        redis = await create_redis_client()
        try:
            yield redis
        finally:
            await redis.close()

    @provide(scope=Scope.APP)
    def get_redis_client(self, redis: Redis) -> RedisClient:
        """
        Provide Redis client wrapper.

        Args:
            redis: Redis connection

        Returns:
            RedisClient instance
        """
        return RedisClient(redis)

    @provide(scope=Scope.REQUEST)
    def get_rate_limiter_repository(
            self, redis_client: RedisClient
    ) -> RateLimiterRepository:
        """
        Provide rate limiter repository.

        Args:
            redis_client: Redis client instance

        Returns:
            RateLimiterRepository instance
        """
        return RateLimiterRepository(redis_client)

    @provide(scope=Scope.REQUEST)
    def get_rate_limiter_service(
            self, repository: RateLimiterRepository
    ) -> RateLimiterService:
        """
        Provide rate limiter service.

        Args:
            repository: Rate limiter repository

        Returns:
            RateLimiterService instance
        """
        return RateLimiterService(repository)