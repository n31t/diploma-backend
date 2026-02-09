"""
Pydantic schemas for user limits and history.
"""

from datetime import datetime
from pydantic import BaseModel, Field


class UserLimitsResponse(BaseModel):
    """Response schema for user limits."""

    daily_limit: int = Field(..., description="Maximum daily requests")
    daily_used: int = Field(..., description="Used daily requests")
    daily_remaining: int = Field(..., description="Remaining daily requests")
    daily_reset_at: datetime = Field(..., description="When daily limit resets")

    monthly_limit: int = Field(..., description="Maximum monthly requests")
    monthly_used: int = Field(..., description="Used monthly requests")
    monthly_remaining: int = Field(..., description="Remaining monthly requests")
    monthly_reset_at: datetime = Field(..., description="When monthly limit resets")

    total_requests: int = Field(..., description="Total lifetime requests")
    is_premium: bool = Field(..., description="Whether user has premium status")
    can_make_request: bool = Field(..., description="Whether user can make more requests")

    class Config:
        json_schema_extra = {
            "example": {
                "daily_limit": 100,
                "daily_used": 25,
                "daily_remaining": 75,
                "daily_reset_at": "2025-02-10T00:00:00Z",
                "monthly_limit": 1000,
                "monthly_used": 150,
                "monthly_remaining": 850,
                "monthly_reset_at": "2025-03-01T00:00:00Z",
                "total_requests": 523,
                "is_premium": False,
                "can_make_request": True
            }
        }


class DetectionHistoryItem(BaseModel):
    """Single history item."""

    id: str
    source: str = Field(..., description="'text' or 'file'")
    file_name: str | None
    result: str = Field(..., description="Detection result")
    confidence: float = Field(..., ge=0.0, le=1.0)
    text_preview: str = Field(..., description="First 200 characters")
    created_at: datetime
    processing_time_ms: int | None = Field(None, description="Processing time in milliseconds")

    class Config:
        from_attributes = True


class DetectionHistoryResponse(BaseModel):
    """Response schema for detection history list."""

    items: list[DetectionHistoryItem]
    total: int
    limit: int
    offset: int


class UserStatsResponse(BaseModel):
    """Response schema for user statistics."""

    total_detections: int
    results_breakdown: dict[str, int]
    average_confidence: float

    class Config:
        json_schema_extra = {
            "example": {
                "total_detections": 150,
                "results_breakdown": {
                    "ai_generated": 45,
                    "human_written": 90,
                    "uncertain": 15
                },
                "average_confidence": 0.847
            }
        }