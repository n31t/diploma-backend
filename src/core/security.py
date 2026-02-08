"""
Security utilities for password hashing and token generation.

This module provides utilities for JWT token creation/validation and password hashing.
"""

from datetime import datetime, timedelta, timezone
from typing import Dict, Any
import secrets

import bcrypt
import jwt

from src.core.config import Config
from src.core.logging import get_logger

logger = get_logger(__name__)


def hash_password(password: str) -> str:
    """
    Hash a password using bcrypt.

    Args:
        password: Plain text password

    Returns:
        Hashed password string
    """
    # Convert password to bytes and hash it
    password_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_bytes, salt)
    # Return as string for storage
    return hashed.decode('utf-8')


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a password against a hash.

    Args:
        plain_password: Plain text password
        hashed_password: Hashed password to compare against

    Returns:
        True if password matches, False otherwise
    """
    try:
        password_bytes = plain_password.encode('utf-8')
        hashed_bytes = hashed_password.encode('utf-8')
        return bcrypt.checkpw(password_bytes, hashed_bytes)
    except Exception as e:
        logger.error("password_verification_failed", error=str(e))
        return False


def create_access_token(data: Dict[str, Any], config: Config) -> str:
    """
    Create a JWT access token.

    Args:
        data: Dictionary containing claims to encode in the token
        config: Application configuration

    Returns:
        Encoded JWT token string
    """
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=config.ACCESS_TOKEN_EXPIRE_MINUTES
    )

    to_encode.update({
        "exp": expire,
        "type": "access"
    })

    logger.debug("creating_access_token", user_id=data.get("sub"), expires_at=expire.isoformat())

    encoded_jwt = jwt.encode(to_encode, config.SECRET_KEY, algorithm=config.ALGORITHM)
    return encoded_jwt


def generate_refresh_token() -> str:
    """
    Generate a cryptographically secure random refresh token.

    Returns:
        URL-safe random token string
    """
    return secrets.token_urlsafe(32)


def decode_access_token(token: str, config: Config) -> Dict[str, Any]:
    """
    Decode and validate a JWT access token.

    Args:
        token: JWT token string
        config: Application configuration

    Returns:
        Decoded token payload

    Raises:
        jwt.ExpiredSignatureError: If token has expired
        jwt.InvalidTokenError: If token is invalid
    """
    try:
        payload = jwt.decode(token, config.SECRET_KEY, algorithms=[config.ALGORITHM])

        if payload.get("type") != "access":
            logger.warning("invalid_token_type", token_type=payload.get("type"))
            raise jwt.InvalidTokenError("Invalid token type")

        return payload

    except jwt.ExpiredSignatureError:
        logger.warning("token_expired")
        raise
    except jwt.InvalidTokenError as e:
        logger.warning("invalid_token", error=str(e))
        raise
