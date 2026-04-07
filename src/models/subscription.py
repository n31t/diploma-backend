"""
Stripe subscription model.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, TimestampMixin, ULIDMixin


class Subscription(ULIDMixin, TimestampMixin, Base):
    __tablename__ = "subscriptions"

    user_id: Mapped[str] = mapped_column(
        String(26),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    stripe_subscription_id: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )

    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="incomplete"
    )

    plan_type: Mapped[str] = mapped_column(
        String(30), nullable=False, default="premium"
    )

    current_period_end: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    cancel_at_period_end: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    def __repr__(self) -> str:
        return (
            f"<Subscription(user_id={self.user_id}, "
            f"status={self.status}, plan={self.plan_type})>"
        )
