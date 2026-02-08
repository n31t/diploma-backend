"""
Authentication helper functions for FastAPI endpoints.

This module provides reusable authentication logic for endpoints using DishkaRoute.
"""

from typing import Optional, TYPE_CHECKING
import jwt
from fastapi import HTTPException, status, Request, Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.core.config import Config
from src.core.logging import get_logger
from src.core.security import decode_access_token
from src.repositories.auth_repository import AuthRepository
from src.dtos.user_dto import AuthenticatedUserDTO


if TYPE_CHECKING:
    from dishka import AsyncContainer

logger = get_logger(__name__)


async def get_authenticated_user_dependency(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer())
) -> AuthenticatedUserDTO:
    """
    FastAPI dependency that authenticates user and returns DTO.

    Args:
        request: FastAPI request object (contains Dishka container)
        credentials: Bearer token credentials from Authorization header

    Returns:
        AuthenticatedUserDTO with user information

    Raises:
        HTTPException: If authentication fails
    """
    # Get Dishka container from request state
    container: Optional[AsyncContainer] = getattr(request.state, "dishka_container", None)

    if not container:
        logger.error("dishka_container_not_found", has_state=hasattr(request, "state"))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error: Dishka container not found"
        )

    # Get config and auth repository from container
    try:
        config: Config = await container.get(Config)
        auth_repository: AuthRepository = await container.get(AuthRepository)

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

        # Fetch user from repository
        user_model = await auth_repository.get_user_by_id(user_id)

        if user_model is None:
            logger.warning("user_not_found", user_id=user_id)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Check if user is active
        if not user_model.is_active:
            logger.warning("user_inactive", user_id=user_model.id)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Inactive user account"
            )

        # Create DTO from user model
        user_dto = AuthenticatedUserDTO(
            id=user_model.id,
            username=user_model.username,
            email=user_model.email,
            is_active=user_model.is_active,
            created_at=user_model.created_at,
            updated_at=user_model.updated_at
        )

        logger.debug(
            "user_authenticated",
            user_id=user_dto.id,
            username=user_dto.username
        )

        return user_dto

    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        logger.error("authentication_error", error=str(e), error_type=type(e).__name__)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication error"
        )
