"""
Authentication repository for database operations.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.auth import User, RefreshToken


class AuthRepository:
    """Repository for authentication-related database operations."""

    def __init__(self, session: AsyncSession):
        self.session: AsyncSession = session

    async def get_user_by_username(self, username: str) -> Optional[User]:
        """
        Get a user by username.

        Args:
            username: Username to search for

        Returns:
            User object or None if not found
        """
        result = await self.session.execute(
            select(User).where(User.username == username)
        )
        return result.scalar_one_or_none()

    async def get_user_by_email(self, email: str) -> Optional[User]:
        """
        Get a user by email.

        Args:
            email: Email to search for

        Returns:
            User object or None if not found
        """
        result = await self.session.execute(
            select(User).where(User.email == email)
        )
        return result.scalar_one_or_none()

    async def create_user(self, username: str, email: str, hashed_password: str) -> User:
        """
        Create a new user in the database.

        Args:
            username: User's username
            email: User's email
            hashed_password: Bcrypt hashed password

        Returns:
            Created User object
        """
        user = User(
            username=username,
            email=email,
            hashed_password=hashed_password,
            is_active=True
        )

        self.session.add(user)
        await self.session.flush()
        await self.session.refresh(user)
        return user

    async def create_refresh_token(
        self,
        user_id: str,
        token: str,
        expires_days: int,
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None
    ) -> RefreshToken:
        """
        Create a new refresh token in the database.

        Args:
            user_id: ID of the user
            token: Refresh token string
            expires_days: Number of days until expiration
            user_agent: User agent string from request
            ip_address: IP address from request

        Returns:
            Created RefreshToken object
        """
        refresh_token = RefreshToken(
            token=token,
            user_id=user_id,
            expires_at=datetime.now(timezone.utc) + timedelta(days=expires_days),
            user_agent=user_agent,
            ip_address=ip_address,
            is_revoked=False
        )

        self.session.add(refresh_token)
        await self.session.flush()
        await self.session.refresh(refresh_token)
        return refresh_token

    async def get_user_by_id(self, user_id: str) -> Optional[User]:
        """
        Get a user by ID.

        Args:
            user_id: User ID

        Returns:
            User object or None if not found
        """
        result = await self.session.execute(
            select(User).where(User.id == user_id)
        )
        return result.scalar_one_or_none()

    # ── Telegram ────────────────────────────────────────────────────────────

    async def update_telegram_connect_token(
        self,
        user_id: str,
        token: str,
        expires_at: datetime,
    ) -> Optional[User]:
        """Store a short-lived connection token on the user row."""
        user = await self.get_user_by_id(user_id)
        if not user:
            return None
        user.telegram_connect_token = token
        user.telegram_connect_token_expires_at = expires_at
        await self.session.flush()
        await self.session.refresh(user)
        return user

    async def get_user_by_telegram_token(self, token: str) -> Optional[User]:
        """Return the user that owns *token* if it hasn't expired yet."""
        now = datetime.now(timezone.utc)
        result = await self.session.execute(
            select(User).where(
                User.telegram_connect_token == token,
                User.telegram_connect_token_expires_at > now,
            )
        )
        return result.scalar_one_or_none()

    async def get_user_by_telegram_chat_id(self, chat_id: str) -> Optional[User]:
        result = await self.session.execute(
            select(User).where(User.telegram_chat_id == chat_id)
        )
        return result.scalar_one_or_none()

    async def connect_telegram_account(self, user_id: str, chat_id: str) -> Optional[User]:
        """Bind *chat_id* to the user and clear the one-time token."""
        user = await self.get_user_by_id(user_id)
        if not user:
            return None
        user.telegram_chat_id = chat_id
        user.telegram_connect_token = None
        user.telegram_connect_token_expires_at = None
        await self.session.flush()
        await self.session.refresh(user)
        return user

    async def disconnect_telegram(self, user_id: str) -> Optional[User]:
        """Remove the Telegram binding for *user_id*."""
        user = await self.get_user_by_id(user_id)
        if not user:
            raise ValueError("User not found")
        user.telegram_chat_id = None
        user.telegram_connect_token = None
        user.telegram_connect_token_expires_at = None
        await self.session.flush()
        await self.session.refresh(user)
        return user