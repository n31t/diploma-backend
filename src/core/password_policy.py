"""
Shared password strength rules for registration and password reset.
"""

import re


def validate_password_strength(password: str) -> str:
    """
    Enforce the same policy as UserRegister.

    Returns:
        The password unchanged if valid.

    Raises:
        ValueError: With a user-facing message if validation fails.
    """
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters long")
    if not re.search(r"[A-Z]", password):
        raise ValueError("Password must contain at least one uppercase letter")
    if not re.search(r"[a-z]", password):
        raise ValueError("Password must contain at least one lowercase letter")
    if not re.search(r"\d", password):
        raise ValueError("Password must contain at least one digit")
    return password
