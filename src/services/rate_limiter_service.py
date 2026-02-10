"""
Rate limiter service for enforcing API rate limits.
"""

from datetime import datetime, timezone

from src.core.logging import get_logger
from src.core.redis_config import redis_config
from src.dtos.rate_limit_dto import (
    RateLimitExceeded,
    RateLimitPeriod,
    RateLimitStatus,
)
from src.repositories.rate_limiter_repository import RateLimiterRepository

logger = get_logger(__name__)


class RateLimiterService:
    """Service for managing rate limiting logic."""

    def __init__(self, rate_limiter_repository: RateLimiterRepository):
        """
        Initialize rate limiter service.

        Args:
            rate_limiter_repository: Repository for rate limit operations
        """
        self.repository = rate_limiter_repository

    async def check_and_increment(self, user_id: str) -> RateLimitStatus:
        """
        Check rate limits and increment if allowed.

        Args:
            user_id: User identifier

        Returns:
            RateLimitStatus with current status

        Raises:
            RateLimitExceeded: If rate limit is exceeded
        """
        if not redis_config.RATE_LIMIT_ENABLED:
            logger.debug("rate_limiting_disabled", user_id=user_id)
            # Return permissive status when disabled
            from src.dtos.rate_limit_dto import RateLimitInfo
            now = datetime.now(timezone.utc)
            dummy_info = RateLimitInfo(
                limit=999999,
                remaining=999999,
                reset_at=now,
                period=RateLimitPeriod.MINUTE
            )
            return RateLimitStatus(
                user_id=user_id,
                is_allowed=True,
                minute_limit=dummy_info,
                hour_limit=dummy_info
            )

        # Get current status
        status = await self.repository.get_rate_limit_status(user_id)

        if not status.is_allowed:
            # Determine which limit was hit
            if not status.minute_limit.remaining:
                limit_info = status.minute_limit
                retry_after = max(1, int((limit_info.reset_at - datetime.now(timezone.utc)).total_seconds()))
                message = (
                    f"Rate limit exceeded: {limit_info.limit} requests per minute. "
                    f"Try again in {retry_after} seconds."
                )
            else:
                limit_info = status.hour_limit
                retry_after = max(1, int((limit_info.reset_at - datetime.now(timezone.utc)).total_seconds()))
                message = (
                    f"Rate limit exceeded: {limit_info.limit} requests per hour. "
                    f"Try again in {retry_after} seconds."
                )

            logger.warning(
                "rate_limit_exceeded",
                user_id=user_id,
                limit=limit_info.limit,
                period=limit_info.period.value,
                retry_after=retry_after
            )

            raise RateLimitExceeded(
                message=message,
                retry_after=retry_after,
                limit_info=limit_info
            )

        # Increment counters for both periods
        await self.repository.increment_rate_limit(user_id, RateLimitPeriod.MINUTE)
        await self.repository.increment_rate_limit(user_id, RateLimitPeriod.HOUR)

        # Get updated status after increment
        updated_status = await self.repository.get_rate_limit_status(user_id)

        logger.info(
            "rate_limit_incremented",
            user_id=user_id,
            minute_remaining=updated_status.minute_limit.remaining,
            hour_remaining=updated_status.hour_limit.remaining
        )

        return updated_status

    async def get_status(self, user_id: str) -> RateLimitStatus:
        """
        Get current rate limit status without incrementing.

        Args:
            user_id: User identifier

        Returns:
            Current RateLimitStatus
        """
        return await self.repository.get_rate_limit_status(user_id)

    async def reset_limits(self, user_id: str) -> None:
        """
        Reset rate limits for user (admin function).

        Args:
            user_id: User identifier
        """
        await self.repository.reset_rate_limits(user_id)
        logger.info("rate_limits_reset_by_admin", user_id=user_id)