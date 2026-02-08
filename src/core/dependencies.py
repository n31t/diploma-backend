"""
Authentication dependencies for FastAPI endpoints.

This module provides dependency injection functions for authenticating users
and extracting user information from JWT tokens.
"""

from typing import Annotated

import jwt
from dishka import FromDishka
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from src.core.config import Config
from src.core.logging import get_logger
from src.core.security import decode_access_token
from src.repositories.auth_repository import AuthRepository
from src.models.auth import User

logger = get_logger(__name__)

# HTTPBearer scheme for extracting tokens from Authorization header
security = HTTPBearer()


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
    auth_repository: FromDishka[AuthRepository],
    config: FromDishka[Config]
) -> User:
    """
    Dependency to get the current authenticated user from JWT token.

    Extracts and validates the JWT token from the Authorization header,
    then fetches the user from the database.

    Args:
        credentials: HTTP Bearer token credentials
        db: Database session

    Returns:
        User object of the authenticated user

    Raises:
        HTTPException 401: If token is invalid, expired, or user not found
        HTTPException 403: If user account is inactive

    Example:
        >>> @router.get("/protected")
        >>> async def protected_route(user: User = Depends(get_current_user)):
        >>>     return {"user_id": user.id}
    """
    token = credentials.credentials

    try:
        # Decode and validate the JWT token
        payload = decode_access_token(token, config)
        user_id: str = payload.get("sub")

        if user_id is None:
            logger.warning("token_missing_user_id")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )

    except jwt.ExpiredSignatureError:
        logger.warning("token_expired")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError as e:
        logger.warning("invalid_token", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Fetch user from database
    user = await auth_repository.get_user_by_id(user_id)

    if user is None:
        logger.warning("user_not_found", user_id=user_id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check if user is active
    if not user.is_active:
        logger.warning("user_inactive", user_id=user.id)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user account"
        )

    logger.debug("user_authenticated", user_id=user.id, username=user.username)
    return user


# Type alias for cleaner endpoint signatures
CurrentUser = Annotated[User, Depends(get_current_user)]
