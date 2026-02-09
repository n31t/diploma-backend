"""
User Limits Data Transfer Objects (DTOs).
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass
class UserLimitDTO:
    """DTO for user limits information."""
    user_id: str
    daily_limit: int
    daily_used: int
    daily_remaining: int
    daily_reset_at: datetime
    monthly_limit: int
    monthly_used: int
    monthly_remaining: int
    monthly_reset_at: datetime
    total_requests: int
    is_premium: bool
    can_make_request: bool

    @classmethod
    def from_model(cls, model):
        """Create DTO from UserLimit model."""
        return cls(
            user_id=model.user_id,
            daily_limit=model.daily_limit,
            daily_used=model.daily_used,
            daily_remaining=max(0, model.daily_limit - model.daily_used),
            daily_reset_at=model.daily_reset_at,
            monthly_limit=model.monthly_limit,
            monthly_used=model.monthly_used,
            monthly_remaining=max(0, model.monthly_limit - model.monthly_used),
            monthly_reset_at=model.monthly_reset_at,
            total_requests=model.total_requests,
            is_premium=model.is_premium,
            can_make_request=(
                    model.daily_used < model.daily_limit and
                    model.monthly_used < model.monthly_limit
            )
        )


@dataclass
class DetectionHistoryDTO:
    """DTO for detection history record."""
    id: str
    user_id: str
    source: str
    file_name: str | None
    result: str
    confidence: float
    text_preview: str
    text_length: int
    word_count: int
    created_at: datetime
    processing_time_ms: int | None