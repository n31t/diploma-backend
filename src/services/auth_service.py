"""
Authentication service layer for business logic.

This service handles authentication-related operations including registration,
login, and token management. Services work with DTOs, not Pydantic schemas.
"""

from __future__ import annotations

from typing import Optional

from src.core.logging import get_logger
from src.core.security import hash_password, verify_password, create_access_token, generate_refresh_token
from src.core.config import Config
from src.dtos import UserRegisterDTO, UserLoginDTO, TokenDTO
from src.repositories.auth_repository import AuthRepository

logger = get_logger(__name__)


class AuthService:
    """Service for managing authentication-related business logic."""

    def __init__(self, auth_repository: AuthRepository, config: Config):
        self.auth_repository = auth_repository
        self.config = config

    async def register_user(
        self,
        user_data: UserRegisterDTO,
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None
    ) -> TokenDTO:
        """
        Register a new user and return authentication tokens.

        Args:
            user_data: User registration DTO
            user_agent: User agent from request headers
            ip_address: IP address from request

        Returns:
            TokenDTO with access and refresh tokens

        Raises:
            ValueError: If username or email already exists

        Example:
            >>> service = AuthService(auth_repository, config)
            >>> dto = UserRegisterDTO(username="john", email="john@example.com", password="SecurePass123")
            >>> tokens = await service.register_user(dto)
        """
        logger.info(
            "registering_user",
            username=user_data.username,
            email=user_data.email
        )

        # Check if username already exists
        existing_user = await self.auth_repository.get_user_by_username(user_data.username)
        if existing_user:
            logger.warning(
                "registration_failed_username_exists",
                username=user_data.username
            )
            raise ValueError("Username already exists")

        # Check if email already exists
        existing_email = await self.auth_repository.get_user_by_email(user_data.email)
        if existing_email:
            logger.warning(
                "registration_failed_email_exists",
                email=user_data.email
            )
            raise ValueError("Email already exists")

        try:
            # Hash the password
            hashed_password = hash_password(user_data.password)

            # Create the user
            user = await self.auth_repository.create_user(
                username=user_data.username,
                email=user_data.email,
                hashed_password=hashed_password
            )

            # Generate tokens
            access_token = create_access_token(
                data={"sub": str(user.id), "username": user.username},
                config=self.config
            )
            refresh_token = generate_refresh_token()

            # Store refresh token
            await self.auth_repository.create_refresh_token(
                user_id=user.id,
                token=refresh_token,
                expires_days=self.config.REFRESH_TOKEN_EXPIRE_DAYS,
                user_agent=user_agent,
                ip_address=ip_address
            )

            logger.info(
                "user_registered_successfully",
                user_id=user.id,
                username=user.username,
                email=user.email
            )

            return TokenDTO(
                access_token=access_token,
                refresh_token=refresh_token
            )

        except Exception as e:
            logger.error(
                "user_registration_failed",
                username=user_data.username,
                email=user_data.email,
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True
            )
            raise

    async def login_user(
        self,
        login_data: UserLoginDTO,
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None
    ) -> TokenDTO:
        """
        Authenticate a user and return authentication tokens.

        Args:
            login_data: User login DTO
            user_agent: User agent from request headers
            ip_address: IP address from request

        Returns:
            TokenDTO with access and refresh tokens

        Raises:
            ValueError: If credentials are invalid or user is inactive

        Example:
            >>> service = AuthService(auth_repository, config)
            >>> dto = UserLoginDTO(username="john", password="SecurePass123")
            >>> tokens = await service.login_user(dto)
        """
        logger.info(
            "login_attempt",
            username=login_data.username,
            ip_address=ip_address
        )

        # Get user by username
        user = await self.auth_repository.get_user_by_username(login_data.username)

        if not user:
            logger.warning(
                "login_failed_user_not_found",
                username=login_data.username,
                ip_address=ip_address
            )
            raise ValueError("Invalid username or password")

        # Verify password
        if not verify_password(login_data.password, user.hashed_password):
            logger.warning(
                "login_failed_invalid_password",
                username=login_data.username,
                user_id=user.id,
                ip_address=ip_address
            )
            raise ValueError("Invalid username or password")

        # Check if user is active
        if not user.is_active:
            logger.warning(
                "login_failed_user_inactive",
                username=login_data.username,
                user_id=user.id,
                ip_address=ip_address
            )
            raise ValueError("Account is inactive")

        try:
            # Generate tokens
            access_token = create_access_token(
                data={"sub": str(user.id), "username": user.username},
                config=self.config
            )
            refresh_token = generate_refresh_token()

            # Store refresh token
            await self.auth_repository.create_refresh_token(
                user_id=user.id,
                token=refresh_token,
                expires_days=self.config.REFRESH_TOKEN_EXPIRE_DAYS,
                user_agent=user_agent,
                ip_address=ip_address
            )

            logger.info(
                "login_successful",
                user_id=user.id,
                username=user.username,
                ip_address=ip_address
            )

            return TokenDTO(
                access_token=access_token,
                refresh_token=refresh_token
            )

        except Exception as e:
            logger.error(
                "login_failed",
                username=login_data.username,
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True
            )
            raise

