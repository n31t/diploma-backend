"""
AI Detection Data Transfer Objects (DTOs).

DTOs for transferring data related to AI text detection.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal, Optional

ExtractionMethod = Literal["newspaper", "bs4_wikipedia", "bs4_generic"]


class DetectionSource(str, Enum):
    """Source of text for detection."""
    TEXT = "text"
    FILE = "file"
    URL = "url"


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
    confidence: float          # 0.0 – 1.0
    text_preview: str          # First 200 chars of analysed text
    source: DetectionSource
    file_name: str | None = None
    metadata: dict | None = None


@dataclass
class URLDetectionRequestDTO:
    """DTO for URL detection request."""
    url: str
    user_id: str


@dataclass
class NewspaperFetchResultDTO:
    """
    DTO returned by NewspaperService after downloading and parsing a URL.

    Fields
    ------
    text:         Extracted plain-text article body (primary output).
    url:          The original URL that was fetched.
    title:        Page / article title, if detected (may be None).
    authors:      List of author names, if detected.
    publish_date: ISO-8601 string representation of the publish date, or None.
    extraction_method: Which extractor produced the winning text.
    fallback_used: True if a non-primary strategy (for this host) produced the text.
    html_truncated: True if raw HTML was capped at download (partial document).
    extraction_rejection_notes: Reasons earlier candidates were rejected (diagnostics).
    """
    text: str
    url: str
    title: Optional[str] = None
    authors: list[str] = field(default_factory=list)
    publish_date: Optional[str] = None
    extraction_method: ExtractionMethod = "newspaper"
    fallback_used: bool = False
    html_truncated: bool = False
    extraction_rejection_notes: list[str] = field(default_factory=list)