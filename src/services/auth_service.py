"""
Authentication service layer for business logic.

This service handles authentication-related operations including registration,
login, and token management. Services work with DTOs, not Pydantic schemas.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from src.core.config import Config
from src.core.logging import get_logger
from src.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    verify_password,
)
from src.dtos import UserLoginDTO, UserRegisterDTO, TokenDTO
from src.dtos.telegram_dto import TelegramConnectDTO, TelegramStatusDTO
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
        ip_address: Optional[str] = None,
    ) -> TokenDTO:
        logger.info("registering_user", username=user_data.username, email=user_data.email)

        if await self.auth_repository.get_user_by_username(user_data.username):
            raise ValueError("Username already exists")
        if await self.auth_repository.get_user_by_email(user_data.email):
            raise ValueError("Email already exists")

        hashed_password = hash_password(user_data.password)
        user = await self.auth_repository.create_user(
            username=user_data.username,
            email=user_data.email,
            hashed_password=hashed_password,
        )

        access_token = create_access_token(
            data={"sub": str(user.id), "username": user.username},
            config=self.config,
        )
        refresh_token = generate_refresh_token()
        await self.auth_repository.create_refresh_token(
            user_id=user.id,
            token=refresh_token,
            expires_days=self.config.REFRESH_TOKEN_EXPIRE_DAYS,
            user_agent=user_agent,
            ip_address=ip_address,
        )

        logger.info("user_registered_successfully", user_id=user.id, username=user.username)
        return TokenDTO(access_token=access_token, refresh_token=refresh_token)

    async def login_user(
        self,
        login_data: UserLoginDTO,
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> TokenDTO:
        logger.info("login_attempt", username=login_data.username, ip_address=ip_address)

        user = await self.auth_repository.get_user_by_username(login_data.username)
        if not user or not verify_password(login_data.password, user.hashed_password):
            raise ValueError("Invalid username or password")
        if not user.is_active:
            raise ValueError("Account is inactive")

        access_token = create_access_token(
            data={"sub": str(user.id), "username": user.username},
            config=self.config,
        )
        refresh_token = generate_refresh_token()
        await self.auth_repository.create_refresh_token(
            user_id=user.id,
            token=refresh_token,
            expires_days=self.config.REFRESH_TOKEN_EXPIRE_DAYS,
            user_agent=user_agent,
            ip_address=ip_address,
        )

        logger.info("login_successful", user_id=user.id, username=user.username)
        return TokenDTO(access_token=access_token, refresh_token=refresh_token)

    # ── Telegram ────────────────────────────────────────────────────────────

    async def generate_telegram_connection_url(self, user_id: str) -> TelegramConnectDTO:
        """
        Generate a one-time deep-link token and return the bot URL.

        The token is stored on the user row and expires after
        ``TELEGRAM_CONNECT_TOKEN_TTL_MINUTES`` minutes.
        """
        if not self.config.TELEGRAM_BOT_USERNAME:
            raise ValueError("Telegram bot is not configured")

        token = secrets.token_hex(16)
        expires_at = datetime.now(timezone.utc) + timedelta(
            minutes=self.config.TELEGRAM_CONNECT_TOKEN_TTL_MINUTES
        )

        user = await self.auth_repository.update_telegram_connect_token(
            user_id=user_id,
            token=token,
            expires_at=expires_at,
        )
        if not user:
            raise ValueError("User not found")

        bot_url = f"https://t.me/{self.config.TELEGRAM_BOT_USERNAME}?start={token}"
        logger.info("telegram_connection_url_generated", user_id=user_id)
        return TelegramConnectDTO(bot_url=bot_url)

    async def get_telegram_status(self, user_id: str) -> TelegramStatusDTO:
        """Return whether the user has a linked Telegram account."""
        user = await self.auth_repository.get_user_by_id(user_id)
        if not user:
            raise ValueError("User not found")
        return TelegramStatusDTO(
            is_connected=bool(user.telegram_chat_id),
            telegram_chat_id=user.telegram_chat_id,
        )

    async def disconnect_telegram(self, user_id: str) -> None:
        """Remove the Telegram binding for the user."""
        logger.info("disconnecting_telegram", user_id=user_id)
        await self.auth_repository.disconnect_telegram(user_id)
        logger.info("telegram_disconnected", user_id=user_id)