"""
Text normalization DTOs.

Dataclasses for the normalization pipeline output: result container,
per-run metadata, quality flags, and structured extraction blocks.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class StructuredBlock:
    """A typed content block produced by format-aware extractors.

    Used to carry table / slide / section structure from the extraction
    layer into the normalization layer so that meaningful markers
    (``[TABLE]``, ``[SLIDE N]``, etc.) can be injected.
    """

    type: str  # "table" | "slide" | "title" | "body" | "notes" | "paragraph"
    content: str
    index: int | None = None


@dataclass(frozen=True)
class QualityFlags:
    """Downstream-relevant boolean signals about the normalized text."""

    short_text: bool = False
    very_short_text: bool = False
    excessive_repetition: bool = False
    mixed_language_possible: bool = False
    low_alpha_ratio: bool = False
    noisy_extraction: bool = False
    mostly_template_text: bool = False
    too_many_short_lines: bool = False
    slide_like_format: bool = False
    table_heavy_content: bool = False


@dataclass(frozen=True)
class NormalizationMetadata:
    """Counters and stats collected during normalization."""

    source_format: str
    original_char_count: int
    normalized_char_count: int
    original_line_count: int
    normalized_line_count: int
    repeated_lines_removed: int = 0
    repeated_paragraphs_removed: int = 0
    headers_footers_removed_count: int = 0
    hyphenation_fixes_count: int = 0
    tables_detected: int = 0
    slides_detected: int = 0


@dataclass(frozen=True)
class NormalizationResult:
    """Immutable container returned by ``TextNormalizationService.normalize``."""

    raw_text: str
    normalized_text: str
    metadata: NormalizationMetadata
    quality_flags: QualityFlags = field(default_factory=QualityFlags)
