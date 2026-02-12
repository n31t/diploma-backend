from dotenv import load_dotenv
from pydantic_settings import BaseSettings
from pydantic import Field
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

    # Telegram Configuration
    TELEGRAM_BOT_TOKEN: Optional[str] = None
    TELEGRAM_BOT_USERNAME: Optional[str] = None  # e.g. "MyNotifyBot" (without @)
    TELEGRAM_CONNECT_TOKEN_TTL_MINUTES: int = 15

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