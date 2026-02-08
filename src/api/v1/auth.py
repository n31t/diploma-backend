"""
Authentication API endpoints.

This module provides endpoints for user registration, login, token refresh,
and other authentication-related operations.
"""

from typing import Annotated

from dishka import FromDishka
from dishka.integrations.fastapi import DishkaRoute
from fastapi import APIRouter, Depends, HTTPException, status, Request

from src.api.v1.schemas.user import UserRegister, UserLogin, TokenResponse, UserResponse
from src.dtos import UserRegisterDTO, UserLoginDTO, AuthenticatedUserDTO
from src.services.auth_service import AuthService
from src.services.shared.auth_helpers import get_authenticated_user_dependency
from src.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(
    prefix="/auth",
    route_class=DishkaRoute,
)


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    user_data: UserRegister,
    request: Request,
    service: FromDishka[AuthService]
):
    """
    Register a new user.
    """
    try:
        # Extract request metadata
        user_agent = request.headers.get("user-agent")
        ip_address = request.client.host if request.client else None

        logger.info(
            "registration_request",
            username=user_data.username,
            email=user_data.email,
            ip_address=ip_address
        )

        # Convert schema to DTO
        user_dto = UserRegisterDTO(**user_data.model_dump())

        # Register user
        token = await service.register_user(
            user_data=user_dto,
            user_agent=user_agent,
            ip_address=ip_address
        )

        logger.info(
            "registration_successful",
            username=user_data.username
        )
        return token

    except ValueError as e:
        logger.warning(
            "registration_validation_error",
            username=user_data.username,
            error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(
            "registration_failed",
            username=user_data.username,
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to register user"
        )


@router.post("/login", response_model=TokenResponse, status_code=status.HTTP_200_OK)
async def login(
    login_data: UserLogin,
    request: Request,
    service: FromDishka[AuthService]
):
    """
    Login a user.
    """
    try:
        # Extract request metadata
        user_agent = request.headers.get("user-agent")
        ip_address = request.client.host if request.client else None

        logger.info(
            "login_request",
            username=login_data.username,
            ip_address=ip_address
        )

        # Convert schema to DTO
        login_dto = UserLoginDTO(**login_data.model_dump())

        # Login user
        token = await service.login_user(
            login_data=login_dto,
            user_agent=user_agent,
            ip_address=ip_address
        )

        logger.info(
            "login_endpoint_successful",
            username=login_data.username
        )

        return token

    except ValueError as e:
        logger.warning(
            "login_authentication_error",
            username=login_data.username,
            error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e)
        )
    except Exception as e:
        logger.error(
            "login_endpoint_failed",
            username=login_data.username,
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to login"
        )


@router.get("/me", response_model=UserResponse, status_code=status.HTTP_200_OK)
async def get_current_user_info(
    user: Annotated[AuthenticatedUserDTO, Depends(get_authenticated_user_dependency)]
):
    """
    Get current authenticated user information.

    The user is automatically authenticated via the bearer token in the Authorization header.
    """
    logger.info(
        "get_current_user_request",
        user_id=user.id,
        username=user.username
    )

    return user
