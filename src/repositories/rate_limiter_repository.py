"""
Rate limiter repository for Redis operations.
"""

from datetime import datetime, timedelta, timezone
from typing import Tuple

from src.core.logging import get_logger
from src.core.redis_config import redis_config
from src.dtos.rate_limit_dto import RateLimitInfo, RateLimitPeriod, RateLimitStatus
from src.infrastructure.redis_client import RedisClient

logger = get_logger(__name__)


class RateLimiterRepository:
    """Repository for rate limiting operations using Redis."""

    def __init__(self, redis_client: RedisClient):
        """
        Initialize rate limiter repository.

        Args:
            redis_client: Redis client instance
        """
        self.redis = redis_client

    def _get_rate_limit_key(self, user_id: str, period: RateLimitPeriod) -> str:
        """
        Generate Redis key for rate limiting.

        Args:
            user_id: User identifier
            period: Time period

        Returns:
            Redis key
        """
        now = datetime.now(timezone.utc)

        if period == RateLimitPeriod.MINUTE:
            time_window = now.strftime("%Y%m%d%H%M")
        elif period == RateLimitPeriod.HOUR:
            time_window = now.strftime("%Y%m%d%H")
        else:  # DAY
            time_window = now.strftime("%Y%m%d")

        return f"rate_limit:{user_id}:{period.value}:{time_window}"

    def _get_ttl_for_period(self, period: RateLimitPeriod) -> int:
        """
        Get TTL in seconds for rate limit period.

        Args:
            period: Time period

        Returns:
            TTL in seconds
        """
        if period == RateLimitPeriod.MINUTE:
            return 60
        elif period == RateLimitPeriod.HOUR:
            return 3600
        else:  # DAY
            return 86400

    def _get_limit_for_period(self, period: RateLimitPeriod) -> int:
        """
        Get rate limit for period.

        Args:
            period: Time period

        Returns:
            Rate limit count
        """
        if period == RateLimitPeriod.MINUTE:
            return redis_config.RATE_LIMIT_PER_MINUTE
        elif period == RateLimitPeriod.HOUR:
            return redis_config.RATE_LIMIT_PER_HOUR
        else:  # DAY
            # Could add daily limit to config
            return redis_config.RATE_LIMIT_PER_HOUR * 24

    def _get_reset_time(self, period: RateLimitPeriod) -> datetime:
        """
        Get reset time for rate limit period.

        Args:
            period: Time period

        Returns:
            Reset datetime
        """
        now = datetime.now(timezone.utc)

        if period == RateLimitPeriod.MINUTE:
            # Reset at next minute
            return (now + timedelta(minutes=1)).replace(second=0, microsecond=0)
        elif period == RateLimitPeriod.HOUR:
            # Reset at next hour
            return (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        else:  # DAY
            # Reset at next day
            return (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)

    async def check_rate_limit(
            self,
            user_id: str,
            period: RateLimitPeriod
    ) -> Tuple[bool, RateLimitInfo]:
        """
        Check if user has exceeded rate limit for period.

        Args:
            user_id: User identifier
            period: Time period to check

        Returns:
            Tuple of (is_allowed, rate_limit_info)
        """
        key = self._get_rate_limit_key(user_id, period)
        limit = self._get_limit_for_period(period)

        # Get current count
        current_str = await self.redis.get(key)
        current = int(current_str) if current_str else 0

        # Check if limit exceeded
        is_allowed = current < limit
        remaining = max(0, limit - current)
        reset_at = self._get_reset_time(period)

        rate_limit_info = RateLimitInfo(
            limit=limit,
            remaining=remaining,
            reset_at=reset_at,
            period=period
        )

        logger.debug(
            "rate_limit_checked",
            user_id=user_id,
            period=period.value,
            current=current,
            limit=limit,
            is_allowed=is_allowed
        )

        return is_allowed, rate_limit_info

    async def increment_rate_limit(self, user_id: str, period: RateLimitPeriod) -> int:
        """
        Increment rate limit counter for user and period.

        Args:
            user_id: User identifier
            period: Time period

        Returns:
            New count after increment
        """
        key = self._get_rate_limit_key(user_id, period)
        ttl_seconds = self._get_ttl_for_period(period)

        # Increment counter
        count = await self.redis.incr(key)

        # Set expiration if this is the first increment
        if count == 1:
            await self.redis.expire(key, ttl_seconds)

        logger.debug(
            "rate_limit_incremented",
            user_id=user_id,
            period=period.value,
            count=count
        )

        return count

    async def get_rate_limit_status(self, user_id: str) -> RateLimitStatus:
        """
        Get complete rate limit status for user.

        Args:
            user_id: User identifier

        Returns:
            RateLimitStatus with all period information
        """
        # Check both minute and hour limits
        minute_allowed, minute_info = await self.check_rate_limit(
            user_id, RateLimitPeriod.MINUTE
        )
        hour_allowed, hour_info = await self.check_rate_limit(
            user_id, RateLimitPeriod.HOUR
        )

        # User is allowed only if both limits pass
        is_allowed = minute_allowed and hour_allowed

        return RateLimitStatus(
            user_id=user_id,
            is_allowed=is_allowed,
            minute_limit=minute_info,
            hour_limit=hour_info
        )

    async def reset_rate_limits(self, user_id: str) -> None:
        """
        Reset all rate limits for user (admin function).

        Args:
            user_id: User identifier
        """
        # Generate all possible keys for current time windows
        keys_to_delete = [
            self._get_rate_limit_key(user_id, RateLimitPeriod.MINUTE),
            self._get_rate_limit_key(user_id, RateLimitPeriod.HOUR),
            self._get_rate_limit_key(user_id, RateLimitPeriod.DAY),
        ]

        deleted = await self.redis.delete(*keys_to_delete)

        logger.info(
            "rate_limits_reset",
            user_id=user_id,
            keys_deleted=deleted
        )