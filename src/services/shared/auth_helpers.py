"""
Authentication helper functions for FastAPI endpoints.

This module provides reusable authentication logic for endpoints using DishkaRoute.
"""

from __future__ import annotations

from typing import Annotated, Optional, TYPE_CHECKING

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.core.config import Config
from src.core.logging import get_logger
from src.core.security import decode_access_token
from src.dtos.user_dto import AuthenticatedUserDTO
from src.repositories.auth_repository import AuthRepository

if TYPE_CHECKING:
    from dishka import AsyncContainer

logger = get_logger(__name__)


async def _build_authenticated_user_dto(
    request: Request,
    credentials: HTTPAuthorizationCredentials,
) -> AuthenticatedUserDTO:
    container: Optional[AsyncContainer] = getattr(request.state, "dishka_container", None)

    if not container:
        logger.error("dishka_container_not_found", has_state=hasattr(request, "state"))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error: Dishka container not found",
        )

    try:
        config: Config = await container.get(Config)
        auth_repository: AuthRepository = await container.get(AuthRepository)
        token = credentials.credentials

        try:
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

        user_model = await auth_repository.get_user_by_id(user_id)

        if user_model is None:
            logger.warning("user_not_found", user_id=user_id)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if not user_model.is_active:
            logger.warning("user_inactive", user_id=user_model.id)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Inactive user account",
            )

        oauth_providers = await auth_repository.list_oauth_providers_for_user(
            user_model.id
        )
        auth_provider_set = set(oauth_providers)
        if user_model.hashed_password:
            auth_provider_set.add("password")
        auth_providers_sorted = sorted(auth_provider_set)

        user_dto = AuthenticatedUserDTO(
            id=user_model.id,
            username=user_model.username,
            email=user_model.email,
            is_active=user_model.is_active,
            is_verified=user_model.is_verified,
            created_at=user_model.created_at,
            updated_at=user_model.updated_at,
            has_password=user_model.hashed_password is not None,
            auth_providers=auth_providers_sorted,
        )

        logger.debug(
            "user_authenticated",
            user_id=user_dto.id,
            username=user_dto.username,
        )

        return user_dto

    except HTTPException:
        raise
    except Exception as e:
        logger.error("authentication_error", error=str(e), error_type=type(e).__name__)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication error",
        )


async def get_authenticated_user_dependency(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer()),
) -> AuthenticatedUserDTO:
    """Authenticate via JWT; allow unverified users (e.g. /me, resend verification)."""
    return await _build_authenticated_user_dto(request, credentials)


async def require_verified_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer()),
) -> AuthenticatedUserDTO:
    """Authenticate and require a confirmed email for core product routes."""
    user = await _build_authenticated_user_dto(request, credentials)
    if not user.is_verified:
        logger.warning("email_not_verified", user_id=user.id)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email address not verified",
        )
    return user


VerifiedUser = Annotated[AuthenticatedUserDTO, Depends(require_verified_user)]
