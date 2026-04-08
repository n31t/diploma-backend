"""
SQLAlchemy models export.

Imports all models in correct order to resolve forward references.
This file must be imported before any individual model usage.
"""

# Import Base first
from src.models.base import Base

# Import models in dependency order
# 1. Independent models (no foreign keys)
from src.models.auth import User, RefreshToken, RegistrationToken, PasswordResetToken
# 2. Dependent models (with foreign keys to User)
from src.models.ai_detection import AIDetectionHistory, UserLimit
from src.models.subscription import Subscription

# Export all models
__all__ = [
    # Base
    "Base",
    # User Management
    "User",
    "RefreshToken",
    "RegistrationToken",
    "PasswordResetToken",
    # AI Detection
    "AIDetectionHistory",
    "UserLimit",
    # Billing
    "Subscription",
]