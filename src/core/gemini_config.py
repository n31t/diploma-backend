from typing import List
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings

class GeminiConfig(BaseSettings):
    GEMINI_API_KEY: str
    GEMINI_MODEL: str = "gemini-2.0-flash-exp"
    MAX_FILE_SIZE_MB: int = 20
    ALLOWED_FILE_EXTENSIONS: List[str]

    class Config:
        env_file = ".env"
        extra = "ignore"

gemini_config = GeminiConfig()
