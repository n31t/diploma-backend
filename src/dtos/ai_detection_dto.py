"""
AI Detection Data Transfer Objects (DTOs).

DTOs for transferring data related to AI text detection.
"""

from dataclasses import dataclass
from enum import Enum


class DetectionSource(str, Enum):
    """Source of text for detection."""
    TEXT = "text"
    FILE = "file"


class DetectionResult(str, Enum):
    """Result of AI detection."""
    AI_GENERATED = "ai_generated"
    HUMAN_WRITTEN = "human_written"
    UNCERTAIN = "uncertain"


@dataclass
class TextExtractionDTO:
    """DTO for extracted text from files."""
    text: str
    source: DetectionSource
    file_name: str | None = None
    file_type: str | None = None


@dataclass
class AIDetectionRequestDTO:
    """DTO for AI detection request."""
    text: str | None = None
    source: DetectionSource = DetectionSource.TEXT


@dataclass
class AIDetectionResultDTO:
    """DTO for AI detection result."""
    result: DetectionResult
    confidence: float  # 0.0 to 1.0
    text_preview: str  # First 200 chars of analyzed text
    source: DetectionSource
    file_name: str | None = None
    metadata: dict | None = None