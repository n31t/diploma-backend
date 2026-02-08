"""
Base classes and mixins for SQLAlchemy models.

Provides common functionality for timestamps, ULIDs, and other shared fields.
"""

from datetime import datetime
from ulid import ULID

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""

    # Type annotation map for common types
    type_annotation_map = {
        datetime: DateTime(timezone=True),
    }


class TimestampMixin:
    """Mixin for models that need created_at and updated_at timestamps."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )


class ULIDMixin:
    """Mixin for models that use ULID as primary key.

    ULID (Universally Unique Lexicographically Sortable Identifier):
    - 26 character string (vs UUID's 36 characters)
    - Lexicographically sortable (can use for ordering by creation time)
    - Case-insensitive, URL-safe
    - 128-bit compatible with UUID
    """

    id: Mapped[str] = mapped_column(
        String(26),  # ULID is 26 characters
        primary_key=True,
        default=lambda: str(ULID()),
        nullable=False
    )


# Backwards compatibility alias
UUIDMixin = ULIDMixin
