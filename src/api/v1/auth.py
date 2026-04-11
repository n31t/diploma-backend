"""
Authentication API endpoints.

This module provides endpoints for user registration, login, token refresh,
and other authentication-related operations.
"""

from typing import Annotated

from dishka import FromDishka
from dishka.integrations.fastapi import DishkaRoute
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import JSONResponse

from src.api.v1.schemas.user import (
    UserRegister,
    UserLogin,
    GoogleOAuthLoginRequest,
    RefreshTokenRequest,
    TokenResponse,
    UserResponse,
    VerifyEmailRequest,
    VerifyEmailResponse,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    ResetPasswordValidateRequest,
    ResetPasswordValidateResponse,
    ResetPasswordRequest,
    ResetPasswordResponse,
)
from src.core.password_reset_error import PasswordResetError
from src.core.google_oauth_error import GoogleOAuthError
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
        user_agent = request.headers.get("user-agent")
        ip_address = request.client.host if request.client else None

        logger.info(
            "registration_request",
            username=user_data.username,
            email=user_data.email,
            ip_address=ip_address
        )

        user_dto = UserRegisterDTO(**user_data.model_dump())

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
        user_agent = request.headers.get("user-agent")
        ip_address = request.client.host if request.client else None

        logger.info(
            "login_request",
            login=login_data.login,
            ip_address=ip_address
        )

        login_dto = UserLoginDTO(**login_data.model_dump())

        token = await service.login_user(
            login_data=login_dto,
            user_agent=user_agent,
            ip_address=ip_address
        )

        logger.info(
            "login_endpoint_successful",
            login=login_data.login
        )

        return token

    except ValueError as e:
        logger.warning(
            "login_authentication_error",
            login=login_data.login,
            error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e)
        )
    except Exception as e:
        logger.error(
            "login_endpoint_failed",
            login=login_data.login,
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to login"
        )


@router.post("/refresh", response_model=TokenResponse, status_code=status.HTTP_200_OK)
async def refresh_tokens(
    body: RefreshTokenRequest,
    request: Request,
    service: FromDishka[AuthService],
):
    """
    Exchange a valid refresh token for a new access token and a new refresh token (rotation).
    """
    try:
        user_agent = request.headers.get("user-agent")
        ip_address = request.client.host if request.client else None
        return await service.refresh_session(
            refresh_token_raw=body.refresh_token,
            user_agent=user_agent,
            ip_address=ip_address,
        )
    except ValueError as e:
        logger.warning("refresh_token_rejected", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as e:
        logger.error(
            "refresh_token_failed",
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to refresh session",
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

    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        is_active=user.is_active,
        is_verified=user.is_verified,
        has_password=user.has_password,
        auth_providers=user.auth_providers,
    )


@router.post("/google", response_model=TokenResponse, status_code=status.HTTP_200_OK)
async def google_oauth_login(
    body: GoogleOAuthLoginRequest,
    request: Request,
    service: FromDishka[AuthService],
):
    """
    Sign in with Google using an authorization code from the frontend.
    Returns the same token pair as email/password login.
    """
    try:
        user_agent = request.headers.get("user-agent")
        ip_address = request.client.host if request.client else None
        return await service.login_with_google_code(
            code=body.code,
            redirect_uri=body.redirect_uri,
            user_agent=user_agent,
            ip_address=ip_address,
        )
    except GoogleOAuthError as e:
        logger.warning("google_oauth_failed", code=e.code)
        return JSONResponse(
            status_code=e.http_status,
            content={"detail": e.message, "code": e.code},
        )
    except Exception as e:
        logger.error(
            "google_oauth_error",
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Google sign-in failed",
        )


@router.post(
    "/verify-email",
    response_model=VerifyEmailResponse,
    status_code=status.HTTP_200_OK,
)
async def verify_email(
    body: VerifyEmailRequest,
    service: FromDishka[AuthService],
):
    """
    Confirm email address using a one-time token from the verification link.
    """
    try:
        await service.verify_email_with_token(body.token)
        return VerifyEmailResponse()
    except ValueError as e:
        logger.warning("verify_email_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(
            "verify_email_error",
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to verify email",
        )


@router.post("/resend-verification", status_code=status.HTTP_204_NO_CONTENT)
async def resend_verification(
    user: Annotated[AuthenticatedUserDTO, Depends(get_authenticated_user_dependency)],
    service: FromDishka[AuthService],
):
    """
    Send a new verification email to the authenticated user.
    """
    try:
        await service.resend_verification_email(user.id)
    except ValueError as e:
        logger.warning("resend_verification_failed", user_id=user.id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(
            "resend_verification_error",
            user_id=user.id,
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to resend verification email",
        )


@router.post(
    "/forgot-password",
    response_model=ForgotPasswordResponse,
    status_code=status.HTTP_200_OK,
)
async def forgot_password(
    body: ForgotPasswordRequest,
    service: FromDishka[AuthService],
):
    """
    Request a password reset email. Response is always the same (no email enumeration).
    """
    await service.request_password_reset(str(body.email))
    return ForgotPasswordResponse()


@router.post(
    "/reset-password/validate",
    response_model=ResetPasswordValidateResponse,
    status_code=status.HTTP_200_OK,
)
async def validate_reset_password_token(
    body: ResetPasswordValidateRequest,
    service: FromDishka[AuthService],
):
    """Check whether a reset token from the email link is still valid."""
    valid, code = await service.validate_password_reset_token(body.token)
    return ResetPasswordValidateResponse(valid=valid, code=code)


@router.post(
    "/reset-password",
    response_model=ResetPasswordResponse,
    status_code=status.HTTP_200_OK,
)
async def reset_password(
    body: ResetPasswordRequest,
    service: FromDishka[AuthService],
):
    """Set a new password using a one-time token from the reset email."""
    try:
        await service.reset_password(body.token, body.password)
        return ResetPasswordResponse()
    except PasswordResetError as e:
        logger.warning(
            "reset_password_failed",
            code=e.code,
        )
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": e.message, "code": e.code},
        )
    except Exception as e:
        logger.error(
            "reset_password_error",
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to reset password",
        )