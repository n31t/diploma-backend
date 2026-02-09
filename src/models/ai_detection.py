"""
AI Detection models for storing detection history and user limits.
"""

from datetime import datetime
from sqlalchemy import String, Integer, Float, Text, ForeignKey, DateTime, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, ULIDMixin, TimestampMixin


class AIDetectionHistory(ULIDMixin, TimestampMixin, Base):
    """
    History of AI detection requests.

    Stores all detection attempts with results for analytics and audit.
    """
    __tablename__ = "ai_detection_history"

    # User who made the request
    user_id: Mapped[str] = mapped_column(
        String(26),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Detection metadata
    source: Mapped[str] = mapped_column(
        String(10),  # 'text' or 'file'
        nullable=False
    )

    file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)  # in bytes
    content_type: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Detection results
    result: Mapped[str] = mapped_column(
        String(20),  # 'ai_generated', 'human_written', 'uncertain'
        nullable=False
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False)

    # Text preview (first 500 chars)
    text_preview: Mapped[str] = mapped_column(Text, nullable=False)
    text_length: Mapped[int] = mapped_column(Integer, nullable=False)
    word_count: Mapped[int] = mapped_column(Integer, nullable=False)

    # Processing metadata
    processing_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)  # milliseconds

    def __repr__(self):
        return f"<AIDetectionHistory(id={self.id}, user_id={self.user_id}, result={self.result})>"


class UserLimit(ULIDMixin, TimestampMixin, Base):
    """
    User limits for AI detection requests.

    Tracks usage and enforces rate limits per user.
    """
    __tablename__ = "user_limits"

    user_id: Mapped[str] = mapped_column(
        String(26),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True
    )

    # Daily limits
    daily_limit: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=100  # Default: 100 requests per day
    )
    daily_used: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0
    )
    daily_reset_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False
    )

    # Monthly limits
    monthly_limit: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1000  # Default: 1000 requests per month
    )
    monthly_used: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0
    )
    monthly_reset_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False
    )

    # Total lifetime usage
    total_requests: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0
    )

    # Premium features
    is_premium: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False
    )

    def __repr__(self):
        return f"<UserLimit(user_id={self.user_id}, daily={self.daily_used}/{self.daily_limit})>"