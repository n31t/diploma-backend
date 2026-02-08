from pydantic import BaseModel, EmailStr, Field, field_validator
import re


class UserRegister(BaseModel):
    """User registration model with validation."""

    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=100)

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        """Validate username format (alphanumeric, underscore, hyphen)."""
        v = v.strip()
        if not re.match(r"^[a-zA-Z0-9_-]+$", v):
            raise ValueError(
                "Username must contain only alphanumeric characters, underscores, and hyphens"
            )
        return v

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        """Validate password complexity."""
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r"[a-z]", v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one digit")
        return v


class TokenResponse(BaseModel):
    """Token response model."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserLogin(BaseModel):
    """User login model."""

    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=1)


class UserResponse(BaseModel):
    """User response model."""

    id: str  # ULID
    username: str
    email: str
    is_active: bool

    class Config:
        from_attributes = True
