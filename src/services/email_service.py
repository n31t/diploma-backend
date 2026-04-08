"""
Pluggable email delivery for verification and other notifications.
"""

from abc import ABC, abstractmethod
from email.message import EmailMessage

import aiosmtplib

from src.core.config import Config
from src.core.logging import get_logger

logger = get_logger(__name__)


class EmailService(ABC):
    """Abstract email sender; inject a real SMTP implementation in production."""

    @abstractmethod
    async def send_verification_email(
        self, *, to: str, token: str, username: str
    ) -> None:
        """Deliver a link where the user can confirm their email address."""

    @abstractmethod
    async def send_password_reset_email(
        self, *, to: str, token: str, username: str
    ) -> None:
        """Deliver a link where the user can set a new password."""


def _verification_url(config: Config, token: str) -> str:
    base = config.FRONTEND_URL.rstrip("/")
    return f"{base}/verify-email?token={token}"


def _reset_url(config: Config, token: str) -> str:
    base = config.FRONTEND_URL.rstrip("/")
    return f"{base}/reset-password?token={token}"


class LoggingEmailService(EmailService):
    """Logs the verification URL (local dev / tests)."""

    def __init__(self, config: Config):
        self._config = config

    async def send_verification_email(
        self, *, to: str, token: str, username: str
    ) -> None:
        url = _verification_url(self._config, token)
        logger.info(
            "verification_email_queued",
            to=to,
            username=username,
            verification_url=url,
        )

    async def send_password_reset_email(
        self, *, to: str, token: str, username: str
    ) -> None:
        url = _reset_url(self._config, token)
        logger.info(
            "password_reset_email_queued",
            to=to,
            username=username,
            reset_url=url,
        )


class SmtpEmailService(EmailService):
    """Production sender over SMTP (STARTTLS on 587 or implicit TLS on 465)."""

    def __init__(self, config: Config):
        self._config = config
        if not config.SMTP_HOST or not config.SMTP_HOST.strip():
            raise ValueError("SMTP_HOST is required for SmtpEmailService")
        self._from_addr = (config.SMTP_FROM_EMAIL or config.SMTP_USER or "").strip()
        if not self._from_addr:
            raise ValueError("SMTP_FROM_EMAIL or SMTP_USER must be set for SMTP sending")

    async def send_verification_email(
        self, *, to: str, token: str, username: str
    ) -> None:
        url = _verification_url(self._config, token)
        app = self._config.APP_NAME
        subject = f"{app}: confirm your email"

        text_body = (
            f"Hi {username},\n\n"
            f"Confirm your email by opening this link:\n{url}\n\n"
            f"If you did not register, you can ignore this message.\n"
        )
        html_body = (
            f"<p>Hi {username},</p>"
            f'<p>Confirm your email by clicking <a href="{url}">this link</a>.</p>'
            f"<p>If you did not register, you can ignore this message.</p>"
        )

        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = self._from_addr
        msg["To"] = to
        msg.set_content(text_body)
        msg.add_alternative(html_body, subtype="html")

        host = self._config.SMTP_HOST.strip()
        port = self._config.SMTP_PORT
        user = self._config.SMTP_USER
        password = self._config.SMTP_PASSWORD

        try:
            if self._config.SMTP_SSL:
                await aiosmtplib.send(
                    msg,
                    hostname=host,
                    port=port,
                    username=user,
                    password=password,
                    use_tls=True,
                    timeout=30,
                )
            else:
                await aiosmtplib.send(
                    msg,
                    hostname=host,
                    port=port,
                    username=user,
                    password=password,
                    start_tls=self._config.SMTP_USE_TLS,
                    timeout=30,
                )
        except Exception as e:
            logger.error(
                "smtp_send_failed",
                to=to,
                host=host,
                port=port,
                error=str(e),
                error_type=type(e).__name__,
            )
            raise

        logger.info("verification_email_sent_smtp", to=to, username=username)

    async def send_password_reset_email(
        self, *, to: str, token: str, username: str
    ) -> None:
        url = _reset_url(self._config, token)
        app = self._config.APP_NAME
        subject = f"{app}: reset your password"

        text_body = (
            f"Hi {username},\n\n"
            f"Reset your password by opening this link:\n{url}\n\n"
            f"If you did not request this, you can ignore this message.\n"
        )
        html_body = (
            f"<p>Hi {username},</p>"
            f'<p>Reset your password by clicking <a href="{url}">this link</a>.</p>'
            f"<p>If you did not request this, you can ignore this message.</p>"
        )

        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = self._from_addr
        msg["To"] = to
        msg.set_content(text_body)
        msg.add_alternative(html_body, subtype="html")

        host = self._config.SMTP_HOST.strip()
        port = self._config.SMTP_PORT
        user = self._config.SMTP_USER
        password = self._config.SMTP_PASSWORD

        try:
            if self._config.SMTP_SSL:
                await aiosmtplib.send(
                    msg,
                    hostname=host,
                    port=port,
                    username=user,
                    password=password,
                    use_tls=True,
                    timeout=30,
                )
            else:
                await aiosmtplib.send(
                    msg,
                    hostname=host,
                    port=port,
                    username=user,
                    password=password,
                    start_tls=self._config.SMTP_USE_TLS,
                    timeout=30,
                )
        except Exception as e:
            logger.error(
                "smtp_password_reset_send_failed",
                to=to,
                host=host,
                port=port,
                error=str(e),
                error_type=type(e).__name__,
            )
            raise

        logger.info("password_reset_email_sent_smtp", to=to, username=username)


def build_email_service(config: Config) -> EmailService:
    """Use SMTP when SMTP_HOST is set; otherwise log the link only."""
    if config.SMTP_HOST and config.SMTP_HOST.strip():
        return SmtpEmailService(config)
    if not config.DEBUG:
        logger.warning(
            "email_using_logging_backend",
            hint="Set SMTP_HOST and credentials to send real mail in production",
        )
    return LoggingEmailService(config)
