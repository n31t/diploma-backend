"""
Rate limiting dependency for FastAPI endpoints.
"""

from typing import Annotated

from dishka import FromDishka
from fastapi import Depends, Request, HTTPException, status

from src.core.logging import get_logger
from src.dtos.rate_limit_dto import RateLimitExceeded
from src.dtos.user_dto import AuthenticatedUserDTO
from src.services.rate_limiter_service import RateLimiterService
from src.services.shared.auth_helpers import get_authenticated_user_dependency

logger = get_logger(__name__)


async def check_rate_limit_dependency(
        request: Request,
        current_user: Annotated[AuthenticatedUserDTO, Depends(get_authenticated_user_dependency)],
) -> None:
    """
    FastAPI dependency to check rate limits.

    Args:
        request: FastAPI request object (contains Dishka container)
        current_user: Authenticated user

    Raises:
        HTTPException 429: If rate limit exceeded
    """
    # Get Dishka container from request state
    container = getattr(request.state, "dishka_container", None)

    if not container:
        logger.warning("rate_limit_check_skipped_no_container", user_id=current_user.id)
        return

    try:
        # Get rate limiter service from container
        rate_limiter_service: RateLimiterService = await container.get(RateLimiterService)

        # Check and increment rate limit
        status_info = await rate_limiter_service.check_and_increment(current_user.id)

        # Add rate limit headers to response (stored in request state for middleware)
        request.state.rate_limit_status = status_info

        logger.debug(
            "rate_limit_check_passed",
            user_id=current_user.id,
            minute_remaining=status_info.minute_limit.remaining,
            hour_remaining=status_info.hour_limit.remaining
        )

    except RateLimitExceeded as e:
        logger.warning(
            "rate_limit_exceeded",
            user_id=current_user.id,
            message=e.message,
            retry_after=e.retry_after
        )

        # Raise HTTP 429 with proper headers
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=e.message,
            headers={
                "Retry-After": str(e.retry_after),
                "X-RateLimit-Limit": str(e.limit_info.limit),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(int(e.limit_info.reset_at.timestamp())),
            }
        )
    except Exception as e:
        logger.error(
            "rate_limit_check_error",
            user_id=current_user.id,
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True
        )
        # Don't block the request on rate limiter errors
        return