"""
SQLAlchemy models export.

Imports all models in correct order to resolve forward references.
This file must be imported before any individual model usage.
"""

# Import Base first
from src.models.base import Base

# Import models in dependency order
# 1. Independent models (no foreign keys)
from src.models.auth import User, RefreshToken, RegistrationToken

# Export all models
__all__ = [
    # Base
    "Base",
    # User Management
    "User",
    "RefreshToken",
    "RegistrationToken",
]
