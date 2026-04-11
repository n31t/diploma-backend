"""
Authentication repository for database operations.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.auth import User, RefreshToken, RegistrationToken, PasswordResetToken, OAuthAccount


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

    async def get_user_by_email_case_insensitive(self, email: str) -> Optional[User]:
        """Match email with trim + case-insensitive comparison (for forgot-password)."""
        key = email.strip().lower()
        result = await self.session.execute(
            select(User).where(func.lower(User.email) == key)
        )
        return result.scalar_one_or_none()

    async def create_user(
        self,
        username: str,
        email: str,
        hashed_password: Optional[str],
        *,
        is_verified: bool = False,
    ) -> User:
        """
        Create a new user in the database.

        Args:
            username: User's username
            email: User's email
            hashed_password: Bcrypt hash, or None for OAuth-only accounts
            is_verified: Email confirmation flag (default False for self-registration)

        Returns:
            Created User object
        """
        user = User(
            username=username,
            email=email,
            hashed_password=hashed_password,
            is_active=True,
            is_verified=is_verified,
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

    async def get_valid_refresh_token_by_value(
        self, token: str
    ) -> Optional[RefreshToken]:
        now = datetime.now(timezone.utc)
        result = await self.session.execute(
            select(RefreshToken).where(
                RefreshToken.token == token,
                RefreshToken.is_revoked.is_(False),
                RefreshToken.expires_at > now,
            )
        )
        return result.scalar_one_or_none()

    async def revoke_refresh_token_by_id(self, token_id: str) -> None:
        await self.session.execute(
            update(RefreshToken)
            .where(RefreshToken.id == token_id)
            .values(is_revoked=True)
        )
        await self.session.flush()

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

    async def create_email_verification_token(
        self,
        user_id: str,
        token: str,
        expires_at: datetime,
    ) -> RegistrationToken:
        row = RegistrationToken(
            token=token,
            user_id=user_id,
            expires_at=expires_at,
            is_used=False,
        )
        self.session.add(row)
        await self.session.flush()
        await self.session.refresh(row)
        return row

    async def get_valid_verification_token_by_value(
        self, token: str
    ) -> Optional[RegistrationToken]:
        now = datetime.now(timezone.utc)
        result = await self.session.execute(
            select(RegistrationToken).where(
                RegistrationToken.token == token,
                RegistrationToken.is_used.is_(False),
                RegistrationToken.expires_at > now,
            )
        )
        return result.scalar_one_or_none()

    async def mark_verification_token_used(self, token_id: str) -> None:
        await self.session.execute(
            update(RegistrationToken)
            .where(RegistrationToken.id == token_id)
            .values(is_used=True)
        )
        await self.session.flush()

    async def revoke_pending_verification_tokens_for_user(self, user_id: str) -> None:
        await self.session.execute(
            update(RegistrationToken)
            .where(
                RegistrationToken.user_id == user_id,
                RegistrationToken.is_used.is_(False),
            )
            .values(is_used=True)
        )
        await self.session.flush()

    async def set_user_verified(self, user_id: str) -> Optional[User]:
        user = await self.get_user_by_id(user_id)
        if not user:
            return None
        user.is_verified = True
        await self.session.flush()
        await self.session.refresh(user)
        return user

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

    async def set_telegram_detection_language(
        self, user_id: str, lang: str
    ) -> Optional[User]:
        """Persist ML detection language for Telegram: ru, kk, or auto."""
        user = await self.get_user_by_id(user_id)
        if not user:
            return None
        user.telegram_detection_language = lang
        await self.session.flush()
        await self.session.refresh(user)
        return user

    async def set_telegram_ui_locale(self, user_id: str, locale: str) -> Optional[User]:
        """Persist UI locale for Telegram bot: ru, kk, or en."""
        user = await self.get_user_by_id(user_id)
        if not user:
            return None
        user.telegram_ui_locale = locale
        await self.session.flush()
        await self.session.refresh(user)
        return user

    async def ensure_telegram_ui_locale_from_client(
        self, user_id: str, telegram_language_code: str | None
    ) -> None:
        """
        If telegram_ui_locale is unset, set it once from Telegram's language_code.

        Mapping: ru -> ru; kk/kz -> kk; else en.
        """
        user = await self.get_user_by_id(user_id)
        if not user or user.telegram_ui_locale is not None:
            return
        user.telegram_ui_locale = map_telegram_language_code_to_ui_locale(
            telegram_language_code
        )
        await self.session.flush()

    # ── Password reset ─────────────────────────────────────────────────────

    async def create_password_reset_token(
        self,
        user_id: str,
        token_hash: str,
        expires_at: datetime,
    ) -> PasswordResetToken:
        row = PasswordResetToken(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
            is_used=False,
        )
        self.session.add(row)
        await self.session.flush()
        await self.session.refresh(row)
        return row

    async def get_password_reset_token_by_hash(
        self, token_hash: str
    ) -> Optional[PasswordResetToken]:
        result = await self.session.execute(
            select(PasswordResetToken).where(
                PasswordResetToken.token_hash == token_hash
            )
        )
        return result.scalar_one_or_none()

    async def invalidate_unused_password_reset_tokens_for_user(
        self, user_id: str
    ) -> None:
        await self.session.execute(
            update(PasswordResetToken)
            .where(
                PasswordResetToken.user_id == user_id,
                PasswordResetToken.is_used.is_(False),
            )
            .values(is_used=True)
        )
        await self.session.flush()

    async def mark_password_reset_token_used(self, token_id: str) -> None:
        await self.session.execute(
            update(PasswordResetToken)
            .where(PasswordResetToken.id == token_id)
            .values(is_used=True)
        )
        await self.session.flush()

    async def update_user_password_hash(
        self, user_id: str, hashed_password: str
    ) -> Optional[User]:
        user = await self.get_user_by_id(user_id)
        if not user:
            return None
        user.hashed_password = hashed_password
        await self.session.flush()
        await self.session.refresh(user)
        return user

    async def revoke_all_refresh_tokens_for_user(self, user_id: str) -> None:
        await self.session.execute(
            update(RefreshToken)
            .where(
                RefreshToken.user_id == user_id,
                RefreshToken.is_revoked.is_(False),
            )
            .values(is_revoked=True)
        )
        await self.session.flush()

    # ── OAuth ──────────────────────────────────────────────────────────────

    async def get_oauth_account(
        self, provider: str, provider_user_id: str
    ) -> Optional[OAuthAccount]:
        result = await self.session.execute(
            select(OAuthAccount).where(
                OAuthAccount.provider == provider,
                OAuthAccount.provider_user_id == provider_user_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_google_oauth_for_user(self, user_id: str) -> Optional[OAuthAccount]:
        result = await self.session.execute(
            select(OAuthAccount).where(
                OAuthAccount.user_id == user_id,
                OAuthAccount.provider == "google",
            )
        )
        return result.scalar_one_or_none()

    async def list_oauth_providers_for_user(self, user_id: str) -> list[str]:
        result = await self.session.execute(
            select(OAuthAccount.provider)
            .where(OAuthAccount.user_id == user_id)
            .distinct()
        )
        return [row[0] for row in result.all()]

    async def create_oauth_account(
        self,
        user_id: str,
        provider: str,
        provider_user_id: str,
        email: str,
    ) -> OAuthAccount:
        row = OAuthAccount(
            user_id=user_id,
            provider=provider,
            provider_user_id=provider_user_id,
            email=email,
        )
        self.session.add(row)
        await self.session.flush()
        await self.session.refresh(row)
        return row

    async def generate_unique_username_from_email(
        self,
        email: str,
        display_name: Optional[str] = None,
    ) -> str:
        """Build a username matching UserRegister rules; append numeric suffix on collision."""
        base: Optional[str] = None
        if display_name and display_name.strip():
            raw = re.sub(r"[^a-zA-Z0-9_-]+", "_", display_name.strip()).strip("_")
            if raw and re.match(r"^[a-zA-Z0-9_-]+$", raw):
                base = raw[:50]
        if not base:
            local = email.split("@", 1)[0]
            raw = re.sub(r"[^a-zA-Z0-9_-]+", "_", local).strip("_")
            if not raw:
                raw = "user"
            base = raw[:50]
        if len(base) < 3:
            base = (base + "_usr")[:50]
        base = base[:50]
        counter = 0
        while True:
            if counter == 0:
                candidate = base
            else:
                suffix = str(counter)
                max_base = 50 - len(suffix)
                candidate = (base[:max_base] + suffix) if max_base > 0 else suffix[-50:]
            if len(candidate) > 50:
                candidate = candidate[:50]
            if not await self.get_user_by_username(candidate):
                return candidate
            counter += 1
            if counter > 10_000:
                raise RuntimeError("Could not allocate unique username")


def map_telegram_language_code_to_ui_locale(code: str | None) -> str:
    """Map Telegram User.language_code to our UI locale (ru | kk | en)."""
    if not code:
        return "en"
    primary = code.lower().split("-")[0]
    if primary == "ru":
        return "ru"
    if primary in ("kk", "kz"):
        return "kk"
    return "en"