"""
Rate limiting middleware to add rate limit headers to responses.
"""

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from src.core.logging import get_logger

logger = get_logger(__name__)


class RateLimitHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware to add rate limit headers to responses."""

    def __init__(self, app: ASGIApp):
        """Initialize middleware."""
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        """
        Add rate limit headers to response.

        Args:
            request: FastAPI request
            call_next: Next middleware/route handler

        Returns:
            Response with rate limit headers
        """
        response = await call_next(request)

        # Check if rate limit status was set by dependency
        rate_limit_status = getattr(request.state, "rate_limit_status", None)

        if rate_limit_status:
            # Determine which limit to show (most restrictive)
            if rate_limit_status.minute_limit.remaining < rate_limit_status.hour_limit.remaining:
                limit_info = rate_limit_status.minute_limit
            else:
                limit_info = rate_limit_status.hour_limit

            # Add headers
            response.headers["X-RateLimit-Limit"] = str(limit_info.limit)
            response.headers["X-RateLimit-Remaining"] = str(limit_info.remaining)
            response.headers["X-RateLimit-Reset"] = str(int(limit_info.reset_at.timestamp()))
            response.headers["X-RateLimit-Period"] = limit_info.period.value

        return response