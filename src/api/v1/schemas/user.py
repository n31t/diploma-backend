from pydantic import BaseModel, EmailStr, Field, field_validator
import re

from src.core.password_policy import validate_password_strength


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
        return validate_password_strength(v)


class TokenResponse(BaseModel):
    """Token response model."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserLogin(BaseModel):
    """User login model. Accepts username or email in the `login` field."""

    login: str = Field(..., min_length=3, max_length=100, description="Username or email")
    password: str = Field(..., min_length=1)


class UserResponse(BaseModel):
    """User response model."""

    id: str  # ULID
    username: str
    email: str
    is_active: bool
    is_verified: bool
    has_password: bool = False
    auth_providers: list[str] = Field(default_factory=list)

    class Config:
        from_attributes = True


class GoogleOAuthLoginRequest(BaseModel):
    """Authorization code from Google Identity Services (web) plus exact redirect_uri."""

    code: str = Field(..., min_length=1, max_length=4096)
    redirect_uri: str = Field(..., min_length=1, max_length=2048)

    @field_validator("code", "redirect_uri")
    @classmethod
    def strip_ws(cls, v: str) -> str:
        return v.strip()


class VerifyEmailRequest(BaseModel):
    """Confirm email using token from the verification link."""

    token: str = Field(..., min_length=10, max_length=512)

    @field_validator("token")
    @classmethod
    def strip_token(cls, v: str) -> str:
        return v.strip()


class VerifyEmailResponse(BaseModel):
    """Acknowledgement after successful email verification."""

    status: str = "ok"


class ForgotPasswordRequest(BaseModel):
    """Request a password reset link (anti-enumeration: same response always)."""

    email: EmailStr


class ForgotPasswordResponse(BaseModel):
    """Neutral acknowledgement; does not reveal whether the email is registered."""

    status: str = "ok"
    message: str = "If an account exists for this email, you will receive reset instructions."


class ResetPasswordValidateRequest(BaseModel):
    """Check whether a reset token from the email link is still usable."""

    token: str = Field(..., min_length=10, max_length=512)

    @field_validator("token")
    @classmethod
    def strip_token(cls, v: str) -> str:
        return v.strip()


class ResetPasswordValidateResponse(BaseModel):
    valid: bool
    code: str | None = None


class ResetPasswordRequest(BaseModel):
    token: str = Field(..., min_length=10, max_length=512)
    password: str = Field(..., min_length=8, max_length=100)

    @field_validator("token")
    @classmethod
    def strip_token(cls, v: str) -> str:
        return v.strip()

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        return validate_password_strength(v)


class ResetPasswordResponse(BaseModel):
    status: str = "ok"
