"""
Rate limiting domain models and exceptions.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class RateLimitPeriod(str, Enum):
    """Rate limit time periods."""
    MINUTE = "minute"
    HOUR = "hour"
    DAY = "day"


@dataclass
class RateLimitInfo:
    """Rate limit information."""
    limit: int
    remaining: int
    reset_at: datetime
    period: RateLimitPeriod


@dataclass
class RateLimitStatus:
    """Complete rate limit status for a user."""
    user_id: str
    is_allowed: bool
    minute_limit: RateLimitInfo
    hour_limit: RateLimitInfo

    @property
    def requests_remaining(self) -> int:
        """Get minimum remaining requests across all periods."""
        return min(self.minute_limit.remaining, self.hour_limit.remaining)


class RateLimitExceeded(Exception):
    """Exception raised when rate limit is exceeded."""

    def __init__(self, message: str, retry_after: int, limit_info: RateLimitInfo):
        """
        Initialize rate limit exception.

        Args:
            message: Error message
            retry_after: Seconds until rate limit resets
            limit_info: Rate limit information
        """
        self.message = message
        self.retry_after = retry_after
        self.limit_info = limit_info
        super().__init__(self.message)