"""
User Data Transfer Objects (DTOs).

DTOs are used to transfer data between service layer and other layers.
They are simple dataclasses without validation logic.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class UserRegisterDTO:
    """DTO for user registration data."""
    username: str
    email: str
    password: str


@dataclass
class UserLoginDTO:
    """DTO for user login data."""
    username: str
    password: str


@dataclass
class UserDTO:
    """DTO for user data."""
    id: str  # ULID
    username: str
    email: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


@dataclass
class TokenDTO:
    """DTO for authentication tokens."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


@dataclass
class RefreshTokenDTO:
    """DTO for refresh token data."""
    id: str  # ULID
    token: str
    user_id: str  # ULID
    expires_at: datetime
    created_at: datetime
    is_revoked: bool
    user_agent: Optional[str] = None
    ip_address: Optional[str] = None


@dataclass
class AuthenticatedUserDTO:
    """DTO for authenticated user with context information."""
    id: str  # ULID
    username: str
    email: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
