"""
Authentication service layer for business logic.

This service handles authentication-related operations including registration,
login, and token management. Services work with DTOs, not Pydantic schemas.
"""

from __future__ import annotations

import asyncio
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from src.core.config import Config
from src.core.email_validation import validate_deliverable_email
from src.core.google_oauth_error import (
    GoogleOAuthError,
    ACCOUNT_INACTIVE,
    GOOGLE_EMAIL_NOT_VERIFIED,
    GOOGLE_OAUTH_DISABLED,
    GOOGLE_OAUTH_NOT_CONFIGURED,
    INVALID_REDIRECT_URI,
    OAUTH_ACCOUNT_CONFLICT,
)
from src.core.logging import get_logger
from src.core.password_policy import validate_password_strength
from src.core.password_reset_error import (
    PasswordResetError,
    RESET_TOKEN_EXPIRED,
    RESET_TOKEN_INVALID,
    RESET_TOKEN_USED,
)
from src.core.security import (
    create_access_token,
    generate_password_reset_token,
    generate_refresh_token,
    generate_verification_token,
    hash_password,
    hash_password_reset_token,
    verify_password,
)
from src.dtos import UserLoginDTO, UserRegisterDTO, TokenDTO
from src.dtos.telegram_dto import TelegramConnectDTO, TelegramStatusDTO
from src.models.auth import User
from src.repositories.auth_repository import AuthRepository
from src.services.email_service import EmailService
from src.services.google_oauth_client import GoogleOAuthClient, GoogleOAuthProfile

logger = get_logger(__name__)

PROVIDER_GOOGLE = "google"


class AuthService:
    """Service for managing authentication-related business logic."""

    def __init__(
        self,
        auth_repository: AuthRepository,
        config: Config,
        email_service: EmailService,
        google_oauth_client: GoogleOAuthClient,
    ):
        self.auth_repository = auth_repository
        self.config = config
        self.email_service = email_service
        self.google_oauth_client = google_oauth_client

    async def register_user(
        self,
        user_data: UserRegisterDTO,
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> TokenDTO:
        logger.info("registering_user", username=user_data.username, email=user_data.email)

        email = user_data.email
        if self.config.EMAIL_CHECK_DELIVERABILITY:
            email = await asyncio.to_thread(
                validate_deliverable_email,
                user_data.email,
                self.config.EMAIL_DNS_VALIDATION_TIMEOUT,
            )

        if await self.auth_repository.get_user_by_username(user_data.username):
            raise ValueError("Username already exists")
        if await self.auth_repository.get_user_by_email(email):
            raise ValueError("Email already exists")

        hashed_password = hash_password(user_data.password)
        user = await self.auth_repository.create_user(
            username=user_data.username,
            email=email,
            hashed_password=hashed_password,
            is_verified=False,
        )
        await self._send_new_verification_email(user)

        logger.info("user_registered_successfully", user_id=user.id, username=user.username)
        return await self._issue_session_tokens(user, user_agent, ip_address)

    async def login_user(
        self,
        login_data: UserLoginDTO,
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> TokenDTO:
        login = login_data.login
        logger.info("login_attempt", login=login, ip_address=ip_address)

        # Определяем: email или username
        if "@" in login:
            user = await self.auth_repository.get_user_by_email(login)
        else:
            user = await self.auth_repository.get_user_by_username(login)

        if not user or not verify_password(login_data.password, user.hashed_password):
            raise ValueError("Invalid credentials")
        if not user.is_active:
            raise ValueError("Account is inactive")

        logger.info("login_successful", user_id=user.id, username=user.username)
        return await self._issue_session_tokens(user, user_agent, ip_address)

    async def _issue_session_tokens(
        self,
        user: User,
        user_agent: Optional[str],
        ip_address: Optional[str],
    ) -> TokenDTO:
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
        expires_in = self.config.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        return TokenDTO(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=expires_in,
        )

    async def refresh_session(
        self,
        refresh_token_raw: str,
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> TokenDTO:
        raw = refresh_token_raw.strip()
        if not raw:
            raise ValueError("Invalid or expired refresh token")
        row = await self.auth_repository.get_valid_refresh_token_by_value(raw)
        if not row:
            raise ValueError("Invalid or expired refresh token")
        user = await self.auth_repository.get_user_by_id(row.user_id)
        if not user:
            raise ValueError("Invalid or expired refresh token")
        if not user.is_active:
            raise ValueError("Account is inactive")
        await self.auth_repository.revoke_refresh_token_by_id(row.id)
        logger.info("refresh_token_rotated", user_id=user.id)
        return await self._issue_session_tokens(user, user_agent, ip_address)

    async def login_with_google_code(
        self,
        code: str,
        redirect_uri: str,
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> TokenDTO:
        if not self.config.GOOGLE_OAUTH_ENABLED:
            raise GoogleOAuthError(
                GOOGLE_OAUTH_DISABLED,
                "Google sign-in is disabled",
                http_status=503,
            )
        cid = (self.config.GOOGLE_CLIENT_ID or "").strip()
        secret = (self.config.GOOGLE_CLIENT_SECRET or "").strip()
        if not cid or not secret:
            raise GoogleOAuthError(
                GOOGLE_OAUTH_NOT_CONFIGURED,
                "Google OAuth is not configured",
            )
        allowed = self.config.google_allowed_redirect_uri_list
        if not allowed:
            raise GoogleOAuthError(
                GOOGLE_OAUTH_NOT_CONFIGURED,
                "No allowed OAuth redirect URIs configured",
            )
        uri = redirect_uri.strip()
        if uri not in allowed:
            raise GoogleOAuthError(
                INVALID_REDIRECT_URI,
                "Redirect URI is not allowed",
            )

        profile = await self.google_oauth_client.exchange_code_for_profile(
            code=code.strip(),
            redirect_uri=uri,
        )
        if not profile.email_verified:
            raise GoogleOAuthError(
                GOOGLE_EMAIL_NOT_VERIFIED,
                "Google email is not verified",
            )

        user = await self._resolve_user_for_google_profile(profile)
        if not user.is_active:
            raise GoogleOAuthError(
                ACCOUNT_INACTIVE,
                "Account is inactive",
                http_status=403,
            )

        logger.info("google_login_successful", user_id=user.id)
        return await self._issue_session_tokens(user, user_agent, ip_address)

    async def _resolve_user_for_google_profile(self, profile: GoogleOAuthProfile) -> User:
        existing_link = await self.auth_repository.get_oauth_account(
            PROVIDER_GOOGLE, profile.sub
        )
        if existing_link:
            user = await self.auth_repository.get_user_by_id(existing_link.user_id)
            if not user:
                raise GoogleOAuthError(
                    OAUTH_ACCOUNT_CONFLICT,
                    "OAuth account is orphaned",
                )
            return user

        existing_user = await self.auth_repository.get_user_by_email_case_insensitive(
            profile.email
        )
        if existing_user:
            google_row = await self.auth_repository.get_google_oauth_for_user(
                existing_user.id
            )
            if google_row and google_row.provider_user_id != profile.sub:
                raise GoogleOAuthError(
                    OAUTH_ACCOUNT_CONFLICT,
                    "This email is already linked to a different Google account",
                )
            if not google_row:
                await self.auth_repository.create_oauth_account(
                    user_id=existing_user.id,
                    provider=PROVIDER_GOOGLE,
                    provider_user_id=profile.sub,
                    email=profile.email,
                )
            if profile.email_verified and not existing_user.is_verified:
                await self.auth_repository.set_user_verified(existing_user.id)
            user = await self.auth_repository.get_user_by_id(existing_user.id)
            assert user is not None
            return user

        username = await self.auth_repository.generate_unique_username_from_email(
            profile.email,
            display_name=profile.name,
        )
        user = await self.auth_repository.create_user(
            username=username,
            email=profile.email,
            hashed_password=None,
            is_verified=True,
        )
        await self.auth_repository.create_oauth_account(
            user_id=user.id,
            provider=PROVIDER_GOOGLE,
            provider_user_id=profile.sub,
            email=profile.email,
        )
        return user

    async def verify_email_with_token(self, token: str) -> None:
        row = await self.auth_repository.get_valid_verification_token_by_value(token)
        if not row:
            raise ValueError("Invalid or expired token")
        user = await self.auth_repository.get_user_by_id(row.user_id)
        if not user:
            raise ValueError("Invalid or expired token")
        if user.is_verified:
            await self.auth_repository.mark_verification_token_used(row.id)
            return
        await self.auth_repository.set_user_verified(user.id)
        await self.auth_repository.mark_verification_token_used(row.id)
        logger.info("email_verified", user_id=user.id)

    async def resend_verification_email(self, user_id: str) -> None:
        user = await self.auth_repository.get_user_by_id(user_id)
        if not user:
            raise ValueError("User not found")
        if user.is_verified:
            raise ValueError("Email already verified")
        await self.auth_repository.revoke_pending_verification_tokens_for_user(user.id)
        await self._send_new_verification_email(user)
        logger.info("verification_email_resent", user_id=user.id)

    async def _send_new_verification_email(self, user: User) -> None:
        raw = generate_verification_token()
        expires_at = datetime.now(timezone.utc) + timedelta(
            hours=self.config.EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS
        )
        await self.auth_repository.create_email_verification_token(
            user_id=user.id,
            token=raw,
            expires_at=expires_at,
        )
        await self.email_service.send_verification_email(
            to=user.email,
            token=raw,
            username=user.username,
        )

    async def request_password_reset(self, email: str) -> None:
        """Queue reset email if the user exists; same outcome for unknown emails (no enumeration)."""
        logger.info("password_reset_requested")
        user = await self.auth_repository.get_user_by_email_case_insensitive(email)
        if not user:
            return
        await self.auth_repository.invalidate_unused_password_reset_tokens_for_user(
            user.id
        )
        raw = generate_password_reset_token()
        token_hash = hash_password_reset_token(raw)
        expires_at = datetime.now(timezone.utc) + timedelta(
            hours=self.config.PASSWORD_RESET_TOKEN_EXPIRE_HOURS
        )
        await self.auth_repository.create_password_reset_token(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        await self.email_service.send_password_reset_email(
            to=user.email,
            token=raw,
            username=user.username,
        )

    async def validate_password_reset_token(
        self, raw_token: str
    ) -> tuple[bool, str | None]:
        """
        Return (True, None) if the token is valid, else (False, error_code).
        Does not reveal whether an email exists in the system.
        """
        token_hash = hash_password_reset_token(raw_token.strip())
        row = await self.auth_repository.get_password_reset_token_by_hash(token_hash)
        if not row:
            return False, RESET_TOKEN_INVALID
        if row.is_used:
            return False, RESET_TOKEN_USED
        now = datetime.now(timezone.utc)
        if row.expires_at <= now:
            return False, RESET_TOKEN_EXPIRED
        return True, None

    async def reset_password(self, raw_token: str, new_password: str) -> None:
        token_hash = hash_password_reset_token(raw_token.strip())
        row = await self.auth_repository.get_password_reset_token_by_hash(token_hash)
        if not row:
            raise PasswordResetError(RESET_TOKEN_INVALID, "Invalid or unknown reset token")
        if row.is_used:
            raise PasswordResetError(RESET_TOKEN_USED, "This reset link has already been used")
        now = datetime.now(timezone.utc)
        if row.expires_at <= now:
            raise PasswordResetError(RESET_TOKEN_EXPIRED, "This reset link has expired")
        validate_password_strength(new_password)
        hashed = hash_password(new_password)
        await self.auth_repository.update_user_password_hash(row.user_id, hashed)
        await self.auth_repository.mark_password_reset_token_used(row.id)
        await self.auth_repository.invalidate_unused_password_reset_tokens_for_user(
            row.user_id
        )
        await self.auth_repository.revoke_all_refresh_tokens_for_user(row.user_id)
        logger.info("password_reset_completed", user_id=row.user_id)

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