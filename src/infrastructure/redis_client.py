"""
Redis client abstraction for clean architecture.
"""

from typing import Optional
from datetime import datetime, timedelta, timezone

import redis.asyncio as redis
from redis.asyncio import Redis

from src.core.logging import get_logger
from src.core.redis_config import redis_config

logger = get_logger(__name__)


class RedisClient:
    """Async Redis client wrapper."""

    def __init__(self, redis_instance: Redis):
        """
        Initialize Redis client.

        Args:
            redis_instance: Redis connection instance
        """
        self._redis = redis_instance

    async def get(self, key: str) -> Optional[str]:
        """
        Get value from Redis.

        Args:
            key: Redis key

        Returns:
            Value or None if not found
        """
        try:
            return await self._redis.get(key)
        except Exception as e:
            logger.error(f"redis_get_error: {e}", key=key)
            raise

    async def set(
            self,
            key: str,
            value: str,
            expire: Optional[int] = None
    ) -> bool:
        """
        Set value in Redis.

        Args:
            key: Redis key
            value: Value to store
            expire: Optional expiration time in seconds

        Returns:
            True if successful
        """
        try:
            return await self._redis.set(key, value, ex=expire)
        except Exception as e:
            logger.error(f"redis_set_error: {e}", key=key)
            raise

    async def incr(self, key: str) -> int:
        """
        Increment value in Redis.

        Args:
            key: Redis key

        Returns:
            New value after increment
        """
        try:
            return await self._redis.incr(key)
        except Exception as e:
            logger.error(f"redis_incr_error: {e}", key=key)
            raise

    async def expire(self, key: str, seconds: int) -> bool:
        """
        Set expiration on key.

        Args:
            key: Redis key
            seconds: Expiration time in seconds

        Returns:
            True if successful
        """
        try:
            return await self._redis.expire(key, seconds)
        except Exception as e:
            logger.error(f"redis_expire_error: {e}", key=key)
            raise

    async def ttl(self, key: str) -> int:
        """
        Get time to live for key.

        Args:
            key: Redis key

        Returns:
            TTL in seconds, -1 if no expiration, -2 if key doesn't exist
        """
        try:
            return await self._redis.ttl(key)
        except Exception as e:
            logger.error(f"redis_ttl_error: {e}", key=key)
            raise

    async def delete(self, *keys: str) -> int:
        """
        Delete keys from Redis.

        Args:
            keys: Keys to delete

        Returns:
            Number of keys deleted
        """
        try:
            return await self._redis.delete(*keys)
        except Exception as e:
            logger.error(f"redis_delete_error: {e}", keys=keys)
            raise

    async def ping(self) -> bool:
        """
        Ping Redis to check connection.

        Returns:
            True if connected
        """
        try:
            return await self._redis.ping()
        except Exception as e:
            logger.error(f"redis_ping_error: {e}")
            return False

    async def close(self):
        """Close Redis connection."""
        await self._redis.close()


async def create_redis_client() -> Redis:
    """
    Create Redis connection.

    Returns:
        Redis client instance
    """
    return await redis.from_url(
        redis_config.redis_url,
        encoding="utf-8",
        decode_responses=redis_config.REDIS_DECODE_RESPONSES,
        max_connections=redis_config.REDIS_MAX_CONNECTIONS,
    )