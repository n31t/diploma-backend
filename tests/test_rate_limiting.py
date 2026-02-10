"""
Tests for rate limiting functionality.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from src.dtos.rate_limit_dto import (
    RateLimitExceeded,
    RateLimitInfo,
    RateLimitPeriod,
    RateLimitStatus,
)
from src.infrastructure.redis_client import RedisClient
from src.repositories.rate_limiter_repository import RateLimiterRepository
from src.services.rate_limiter_service import RateLimiterService


@pytest.fixture
def mock_redis_client():
    """Create mock Redis client."""
    client = AsyncMock(spec=RedisClient)
    return client


@pytest.fixture
def rate_limiter_repository(mock_redis_client):
    """Create rate limiter repository with mock Redis."""
    return RateLimiterRepository(mock_redis_client)


@pytest.fixture
def rate_limiter_service(rate_limiter_repository):
    """Create rate limiter service."""
    return RateLimiterService(rate_limiter_repository)


class TestRateLimiterRepository:
    """Test rate limiter repository."""

    @pytest.mark.asyncio
    async def test_check_rate_limit_within_limit(self, rate_limiter_repository, mock_redis_client):
        """Test checking rate limit when within limit."""
        # Mock Redis to return current count of 5
        mock_redis_client.get.return_value = "5"

        user_id = "test_user"
        is_allowed, limit_info = await rate_limiter_repository.check_rate_limit(
            user_id, RateLimitPeriod.MINUTE
        )

        assert is_allowed is True
        assert limit_info.limit == 10  # Default limit
        assert limit_info.remaining == 5  # 10 - 5
        assert limit_info.period == RateLimitPeriod.MINUTE

    @pytest.mark.asyncio
    async def test_check_rate_limit_at_limit(self, rate_limiter_repository, mock_redis_client):
        """Test checking rate limit when at limit."""
        # Mock Redis to return current count of 10
        mock_redis_client.get.return_value = "10"

        user_id = "test_user"
        is_allowed, limit_info = await rate_limiter_repository.check_rate_limit(
            user_id, RateLimitPeriod.MINUTE
        )

        assert is_allowed is False
        assert limit_info.remaining == 0

    @pytest.mark.asyncio
    async def test_check_rate_limit_no_previous_requests(self, rate_limiter_repository, mock_redis_client):
        """Test checking rate limit with no previous requests."""
        # Mock Redis to return None (no key exists)
        mock_redis_client.get.return_value = None

        user_id = "test_user"
        is_allowed, limit_info = await rate_limiter_repository.check_rate_limit(
            user_id, RateLimitPeriod.MINUTE
        )

        assert is_allowed is True
        assert limit_info.remaining == 10  # Full limit

    @pytest.mark.asyncio
    async def test_increment_rate_limit_first_time(self, rate_limiter_repository, mock_redis_client):
        """Test incrementing rate limit for first time."""
        # Mock Redis incr to return 1 (first increment)
        mock_redis_client.incr.return_value = 1

        user_id = "test_user"
        count = await rate_limiter_repository.increment_rate_limit(
            user_id, RateLimitPeriod.MINUTE
        )

        assert count == 1
        # Verify expire was called
        mock_redis_client.expire.assert_called_once()

    @pytest.mark.asyncio
    async def test_increment_rate_limit_subsequent(self, rate_limiter_repository, mock_redis_client):
        """Test incrementing rate limit for subsequent requests."""
        # Mock Redis incr to return 5 (not first increment)
        mock_redis_client.incr.return_value = 5

        user_id = "test_user"
        count = await rate_limiter_repository.increment_rate_limit(
            user_id, RateLimitPeriod.MINUTE
        )

        assert count == 5
        # Expire should not be called for subsequent increments
        mock_redis_client.expire.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_rate_limit_status(self, rate_limiter_repository, mock_redis_client):
        """Test getting complete rate limit status."""
        # Mock minute and hour counts
        mock_redis_client.get.side_effect = ["3", "25"]  # minute, hour

        user_id = "test_user"
        status = await rate_limiter_repository.get_rate_limit_status(user_id)

        assert status.user_id == user_id
        assert status.is_allowed is True
        assert status.minute_limit.remaining == 7  # 10 - 3
        assert status.hour_limit.remaining == 75  # 100 - 25

    @pytest.mark.asyncio
    async def test_get_rate_limit_status_minute_exceeded(self, rate_limiter_repository, mock_redis_client):
        """Test status when minute limit exceeded."""
        # Mock minute limit exceeded
        mock_redis_client.get.side_effect = ["10", "25"]  # minute at limit, hour ok

        user_id = "test_user"
        status = await rate_limiter_repository.get_rate_limit_status(user_id)

        assert status.is_allowed is False  # Minute limit hit
        assert status.minute_limit.remaining == 0

    @pytest.mark.asyncio
    async def test_reset_rate_limits(self, rate_limiter_repository, mock_redis_client):
        """Test resetting rate limits."""
        mock_redis_client.delete.return_value = 3

        user_id = "test_user"
        await rate_limiter_repository.reset_rate_limits(user_id)

        mock_redis_client.delete.assert_called_once()


class TestRateLimiterService:
    """Test rate limiter service."""

    @pytest.mark.asyncio
    async def test_check_and_increment_success(self, rate_limiter_service, rate_limiter_repository):
        """Test successful rate limit check and increment."""
        # Mock repository to return allowed status
        mock_status = MagicMock(spec=RateLimitStatus)
        mock_status.is_allowed = True
        mock_status.minute_limit = MagicMock(remaining=5)
        mock_status.hour_limit = MagicMock(remaining=50)

        rate_limiter_repository.get_rate_limit_status = AsyncMock(return_value=mock_status)
        rate_limiter_repository.increment_rate_limit = AsyncMock()

        user_id = "test_user"
        result = await rate_limiter_service.check_and_increment(user_id)

        assert result.is_allowed is True
        # Verify increment was called for both periods
        assert rate_limiter_repository.increment_rate_limit.call_count == 2

    @pytest.mark.asyncio
    async def test_check_and_increment_minute_exceeded(self, rate_limiter_service, rate_limiter_repository):
        """Test rate limit exceeded for minute period."""
        # Create mock limit info for minute
        mock_minute_limit = RateLimitInfo(
            limit=10,
            remaining=0,
            reset_at=datetime.now(timezone.utc),
            period=RateLimitPeriod.MINUTE
        )

        mock_hour_limit = RateLimitInfo(
            limit=100,
            remaining=50,
            reset_at=datetime.now(timezone.utc),
            period=RateLimitPeriod.HOUR
        )

        mock_status = RateLimitStatus(
            user_id="test_user",
            is_allowed=False,
            minute_limit=mock_minute_limit,
            hour_limit=mock_hour_limit
        )

        rate_limiter_repository.get_rate_limit_status = AsyncMock(return_value=mock_status)

        user_id = "test_user"
        with pytest.raises(RateLimitExceeded) as exc_info:
            await rate_limiter_service.check_and_increment(user_id)

        assert "minute" in str(exc_info.value.message).lower()
        assert exc_info.value.retry_after > 0

    @pytest.mark.asyncio
    async def test_check_and_increment_hour_exceeded(self, rate_limiter_service, rate_limiter_repository):
        """Test rate limit exceeded for hour period."""
        mock_minute_limit = RateLimitInfo(
            limit=10,
            remaining=5,
            reset_at=datetime.now(timezone.utc),
            period=RateLimitPeriod.MINUTE
        )

        mock_hour_limit = RateLimitInfo(
            limit=100,
            remaining=0,
            reset_at=datetime.now(timezone.utc),
            period=RateLimitPeriod.HOUR
        )

        mock_status = RateLimitStatus(
            user_id="test_user",
            is_allowed=False,
            minute_limit=mock_minute_limit,
            hour_limit=mock_hour_limit
        )

        rate_limiter_repository.get_rate_limit_status = AsyncMock(return_value=mock_status)

        user_id = "test_user"
        with pytest.raises(RateLimitExceeded) as exc_info:
            await rate_limiter_service.check_and_increment(user_id)

        assert "hour" in str(exc_info.value.message).lower()

    @pytest.mark.asyncio
    async def test_get_status(self, rate_limiter_service, rate_limiter_repository):
        """Test getting rate limit status without incrementing."""
        mock_status = MagicMock(spec=RateLimitStatus)
        rate_limiter_repository.get_rate_limit_status = AsyncMock(return_value=mock_status)
        rate_limiter_repository.increment_rate_limit = AsyncMock()

        user_id = "test_user"
        result = await rate_limiter_service.get_status(user_id)

        assert result == mock_status
        # Verify no increment was called
        rate_limiter_repository.increment_rate_limit.assert_not_called()

    @pytest.mark.asyncio
    async def test_reset_limits(self, rate_limiter_service, rate_limiter_repository):
        """Test resetting user limits."""
        rate_limiter_repository.reset_rate_limits = AsyncMock()

        user_id = "test_user"
        await rate_limiter_service.reset_limits(user_id)

        rate_limiter_repository.reset_rate_limits.assert_called_once_with(user_id)


class TestRateLimitDTO:
    """Test rate limit DTOs."""

    def test_rate_limit_status_requests_remaining(self):
        """Test requests_remaining property."""
        minute_limit = RateLimitInfo(
            limit=10,
            remaining=3,
            reset_at=datetime.now(timezone.utc),
            period=RateLimitPeriod.MINUTE
        )

        hour_limit = RateLimitInfo(
            limit=100,
            remaining=50,
            reset_at=datetime.now(timezone.utc),
            period=RateLimitPeriod.HOUR
        )

        status = RateLimitStatus(
            user_id="test_user",
            is_allowed=True,
            minute_limit=minute_limit,
            hour_limit=hour_limit
        )

        # Should return minimum (most restrictive)
        assert status.requests_remaining == 3

    def test_rate_limit_exceeded_exception(self):
        """Test RateLimitExceeded exception."""
        limit_info = RateLimitInfo(
            limit=10,
            remaining=0,
            reset_at=datetime.now(timezone.utc),
            period=RateLimitPeriod.MINUTE
        )

        exc = RateLimitExceeded(
            message="Rate limit exceeded",
            retry_after=60,
            limit_info=limit_info
        )

        assert exc.message == "Rate limit exceeded"
        assert exc.retry_after == 60
        assert exc.limit_info == limit_info

