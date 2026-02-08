"""
Pydantic schemas for AI detection API.

These schemas handle request validation and response formatting.
"""

from enum import Enum

from pydantic import BaseModel, Field, field_validator


class DetectionSourceSchema(str, Enum):
    """Source of text for detection."""
    TEXT = "text"
    FILE = "file"


class DetectionResultSchema(str, Enum):
    """Result of AI detection."""
    AI_GENERATED = "ai_generated"
    HUMAN_WRITTEN = "human_written"
    UNCERTAIN = "uncertain"


class TextDetectionRequest(BaseModel):
    """Request schema for text-based detection."""

    text: str = Field(
        ...,
        min_length=50,
        description="Text to analyze for AI detection"
    )

    @field_validator("text")
    @classmethod
    def validate_text_content(cls, v: str) -> str:
        """Validate text content."""
        if not v.strip():
            raise ValueError("Text cannot be empty or whitespace only")
        return v.strip()


class AIDetectionResponse(BaseModel):
    """Response schema for AI detection results."""

    result: DetectionResultSchema = Field(
        ...,
        description="Detection result: ai_generated, human_written, or uncertain"
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence score between 0.0 and 1.0"
    )
    text_preview: str = Field(
        ...,
        description="Preview of the analyzed text (first 200 characters)"
    )
    source: DetectionSourceSchema = Field(
        ...,
        description="Source of the text: text or file"
    )
    file_name: str | None = Field(
        None,
        description="Name of the uploaded file (if applicable)"
    )
    metadata: dict | None = Field(
        None,
        description="Additional metadata about the detection"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "result": "ai_generated",
                "confidence": 0.87,
                "text_preview": "This is a sample text that has been analyzed...",
                "source": "text",
                "file_name": None,
                "metadata": {
                    "text_length": 1250,
                    "word_count": 215
                }
            }
        }


class ErrorResponse(BaseModel):
    """Error response schema."""

    detail: str = Field(
        ...,
        description="Error message"
    )
    error_type: str | None = Field(
        None,
        description="Type of error"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "detail": "File size exceeds maximum allowed size",
                "error_type": "ValueError"
            }
        }