from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings
from typing import Optional

load_dotenv()


class Config(BaseSettings):
    APP_NAME: str = "Testing"
    DEBUG: bool = False
    DB_USER: str
    DB_PASSWORD: str
    DB_NAME: str
    DB_HOST: str
    DB_PORT: int = 5432

    # JWT Configuration
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS: int = 48
    PASSWORD_RESET_TOKEN_EXPIRE_HOURS: int = 24
    # Registration: DNS check that the domain exists and can receive mail (email-validator).
    EMAIL_CHECK_DELIVERABILITY: bool = True
    EMAIL_DNS_VALIDATION_TIMEOUT: int = Field(default=10, ge=1, le=120)

    # Telegram Configuration
    TELEGRAM_BOT_TOKEN: Optional[str] = None
    TELEGRAM_BOT_USERNAME: Optional[str] = None  # e.g. "MyNotifyBot" (without @)
    TELEGRAM_CONNECT_TOKEN_TTL_MINUTES: int = 15

    # Stripe Configuration
    STRIPE_SECRET_KEY: Optional[str] = None
    STRIPE_WEBHOOK_SECRET: Optional[str] = None
    STRIPE_PRICE_ID: Optional[str] = None
    FRONTEND_URL: str = "http://localhost:3000"

    # SMTP (optional). If SMTP_HOST is set, verification emails are sent via SMTP.
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: int = 587
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_FROM_EMAIL: Optional[str] = None
    SMTP_USE_TLS: bool = True
    SMTP_SSL: bool = False

    # Google Sign-In (authorization code flow; optional)
    GOOGLE_OAUTH_ENABLED: bool = False
    GOOGLE_CLIENT_ID: Optional[str] = None
    GOOGLE_CLIENT_SECRET: Optional[str] = None
    # Comma-separated exact redirect_uri values allowed (e.g. postmessage,https://app/callback)
    GOOGLE_ALLOWED_REDIRECT_URIS: str = ""

    @property
    def google_allowed_redirect_uri_list(self) -> list[str]:
        raw = (self.GOOGLE_ALLOWED_REDIRECT_URIS or "").strip()
        if not raw:
            return []
        return [part.strip() for part in raw.split(",") if part.strip()]

    @property
    def db_url(self):
        return f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

    @property
    def telegram_token(self):
        """Alias kept for backward compatibility with TelegramBotService."""
        return self.TELEGRAM_BOT_TOKEN

    @property
    def telegram_bot_username(self):
        return self.TELEGRAM_BOT_USERNAME

config = Config()