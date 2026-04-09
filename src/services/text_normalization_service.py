"""
Text normalization service for the AI-detection pipeline.

Purpose
-------
Reduce extraction noise while **preserving authorship / style signals** that
the downstream AI-vs-human classifier relies on.  Every step is intentionally
conservative — when in doubt we keep the text unchanged.

Pipeline order
--------------
1. Unicode NFKC normalization — canonical form, safe for any language.
2. Whitespace normalization — collapse runs of spaces/tabs, NBSP → space,
   trim trailing whitespace, collapse excessive blank lines while keeping
   paragraph separation.
3. Hyphenation repair — rejoin ``word-\\nword`` that was split by a line
   break (only lowercase continuation, never across paragraph boundaries).
4. Boilerplate removal — frequency-based detection of repeated short lines
   (page numbers, headers/footers, watermarks).
5. Paragraph deduplication — remove exact consecutive duplicate paragraphs
   caused by extraction artifacts.
6. Structure markers — inject ``[TABLE]``, ``[SLIDE N]`` etc. from
   structured blocks provided by the extraction layer.
7. HTML residual cleanup — strip leftover script/style/nav text (html only).
8. Quality flags — compute downstream-relevant boolean signals.
9. Metadata — collect counters accumulated during the pipeline.

What is intentionally NOT done
------------------------------
- No global lowercasing.
- No stemming / lemmatization.
- No stop-word removal.
- No spell correction.
- No paraphrasing / summarization / translation.
- No punctuation stripping.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass

from src.core.logging import get_logger
from src.dtos.normalization_dto import (
    NormalizationMetadata,
    NormalizationResult,
    QualityFlags,
    StructuredBlock,
)

logger = get_logger(__name__)

# ── Thresholds ──────────────────────────────────────────────────────────────

_SHORT_TEXT_CHARS = 200
_VERY_SHORT_TEXT_CHARS = 50
_LOW_ALPHA_THRESHOLD = 0.5
_BOILERPLATE_MAX_LINE_LEN = 80
_BOILERPLATE_MIN_OCCURRENCES = 3
_SHORT_LINE_LEN = 40
_SHORT_LINE_RATIO = 0.7
_REPETITION_RATIO = 0.4  # fraction of lines that are duplicates


# ── Compiled patterns (module-level, built once) ────────────────────────────

_NBSP = re.compile(r"\u00a0")
_HORIZONTAL_WS_RUN = re.compile(r"[ \t]+")
_TRAILING_WS = re.compile(r"[ \t]+$", re.MULTILINE)
_MULTI_BLANK = re.compile(r"\n{3,}")
_HYPHEN_BREAK = re.compile(
    r"(\w)-\n([a-z\u0430-\u044f\u04d9\u04e9\u04b1\u0456\u049b\u04a3\u04af\u04bb])",
)
_PAGE_NUMBER = re.compile(r"^\s*-?\s*\d{1,4}\s*-?\s*$")
_HTML_RESIDUAL_TAG = re.compile(r"<(script|style|noscript|nav)[^>]*>[\s\S]*?</\1>", re.IGNORECASE)


# ── Internal counter bag ───────────────────────────────────────────────────

@dataclass
class _Counters:
    repeated_lines_removed: int = 0
    repeated_paragraphs_removed: int = 0
    headers_footers_removed_count: int = 0
    hyphenation_fixes_count: int = 0
    tables_detected: int = 0
    slides_detected: int = 0


# ── Service ─────────────────────────────────────────────────────────────────

class TextNormalizationService:
    """Deterministic, style-preserving text normalization for AI detection."""

    def normalize(
        self,
        raw_text: str,
        source_format: str,
        structured_blocks: list[StructuredBlock] | None = None,
    ) -> NormalizationResult:
        """Normalize extracted text and compute quality metadata.

        Args:
            raw_text:          The unchanged text produced by the extraction layer.
            source_format:     One of ``docx``, ``pptx``, ``txt``, ``html``,
                               ``pdf``, ``text``, ``url``.
            structured_blocks: Optional typed blocks (tables, slides) from the
                               extraction layer.

        Returns:
            A :class:`NormalizationResult` with raw text, normalized text,
            metadata counters, and quality flags.
        """
        counters = _Counters()

        text = raw_text

        text = self._normalize_unicode(text)
        text = self._normalize_whitespace(text)
        text, counters.hyphenation_fixes_count = self._fix_hyphenation(text)
        text, counters.headers_footers_removed_count = self._remove_boilerplate(text, source_format)
        text, counters.repeated_lines_removed = self._deduplicate_lines(text)
        text, counters.repeated_paragraphs_removed = self._deduplicate_paragraphs(text)

        if structured_blocks:
            text, counters.tables_detected, counters.slides_detected = (
                self._inject_structure_markers(text, source_format, structured_blocks)
            )

        if source_format == "html":
            text = self._strip_html_residual(text)

        text = text.strip()

        quality_flags = self._compute_quality_flags(
            raw_text, text, source_format, structured_blocks,
        )
        metadata = self._compute_metadata(
            raw_text, text, source_format, counters, structured_blocks,
        )

        logger.info(
            "text_normalized",
            source_format=source_format,
            original_chars=metadata.original_char_count,
            normalized_chars=metadata.normalized_char_count,
            hyphenation_fixes=counters.hyphenation_fixes_count,
            boilerplate_removed=counters.headers_footers_removed_count,
            repeated_lines=counters.repeated_lines_removed,
            repeated_paragraphs=counters.repeated_paragraphs_removed,
        )

        return NormalizationResult(
            raw_text=raw_text,
            normalized_text=text,
            metadata=metadata,
            quality_flags=quality_flags,
        )

    # ── Pipeline steps ──────────────────────────────────────────────────────

    @staticmethod
    def _normalize_unicode(text: str) -> str:
        return unicodedata.normalize("NFKC", text)

    @staticmethod
    def _normalize_whitespace(text: str) -> str:
        text = _NBSP.sub(" ", text)
        text = _TRAILING_WS.sub("", text)
        lines = text.split("\n")
        normalized: list[str] = []
        for line in lines:
            normalized.append(_HORIZONTAL_WS_RUN.sub(" ", line))
        text = "\n".join(normalized)
        text = _MULTI_BLANK.sub("\n\n", text)
        return text

    @staticmethod
    def _fix_hyphenation(text: str) -> tuple[str, int]:
        count = 0

        def _rejoin(m: re.Match) -> str:
            nonlocal count
            count += 1
            return m.group(1) + m.group(2)

        text = _HYPHEN_BREAK.sub(_rejoin, text)
        return text, count

    @staticmethod
    def _remove_boilerplate(text: str, source_format: str) -> tuple[str, int]:
        if source_format in ("text", "url"):
            return text, 0

        lines = text.split("\n")
        short_lines: list[str] = []
        for line in lines:
            stripped = line.strip()
            if stripped and len(stripped) <= _BOILERPLATE_MAX_LINE_LEN:
                short_lines.append(stripped)

        freq = Counter(short_lines)
        boilerplate: set[str] = set()
        for line_text, cnt in freq.items():
            if cnt >= _BOILERPLATE_MIN_OCCURRENCES:
                boilerplate.add(line_text)

        # Standalone page numbers (e.g. "1", "- 2 -") are noise regardless of
        # how many times they occur.
        for line in lines:
            stripped = line.strip()
            if stripped and _PAGE_NUMBER.match(stripped):
                boilerplate.add(stripped)

        if not boilerplate:
            return text, 0

        removed = 0
        kept: list[str] = []
        for line in lines:
            if line.strip() in boilerplate:
                removed += 1
            else:
                kept.append(line)

        return "\n".join(kept), removed

    @staticmethod
    def _deduplicate_lines(text: str) -> tuple[str, int]:
        lines = text.split("\n")
        result: list[str] = []
        removed = 0
        prev: str | None = None
        for line in lines:
            stripped = line.strip()
            if stripped and stripped == prev:
                removed += 1
                continue
            result.append(line)
            prev = stripped if stripped else None
        return "\n".join(result), removed

    @staticmethod
    def _deduplicate_paragraphs(text: str) -> tuple[str, int]:
        paragraphs = re.split(r"\n{2,}", text)
        result: list[str] = []
        removed = 0
        prev: str | None = None
        for para in paragraphs:
            normed = para.strip()
            if normed and normed == prev:
                removed += 1
                continue
            result.append(para)
            prev = normed if normed else None
        return "\n\n".join(result), removed

    @staticmethod
    def _inject_structure_markers(
        text: str,
        source_format: str,
        blocks: list[StructuredBlock],
    ) -> tuple[str, int, int]:
        tables = 0
        slides = 0

        parts: list[str] = [text] if text.strip() else []

        for block in blocks:
            if block.type == "table":
                tables += 1
                parts.append(f"[TABLE]\n{block.content}\n[/TABLE]")
            elif block.type == "slide":
                slides += 1
                idx = block.index if block.index is not None else slides
                parts.append(f"[SLIDE {idx}]\n{block.content}\n[/SLIDE]")
            elif block.type == "title":
                parts.append(f"[TITLE] {block.content}")
            elif block.type == "body":
                parts.append(f"[BODY]\n{block.content}\n[/BODY]")
            elif block.type == "notes":
                parts.append(f"[NOTES]\n{block.content}\n[/NOTES]")

        return "\n\n".join(parts), tables, slides

    @staticmethod
    def _strip_html_residual(text: str) -> str:
        return _HTML_RESIDUAL_TAG.sub("", text)

    # ── Quality flags ───────────────────────────────────────────────────────

    @staticmethod
    def _compute_quality_flags(
        raw_text: str,
        normalized_text: str,
        source_format: str,
        blocks: list[StructuredBlock] | None,
    ) -> QualityFlags:
        n_chars = len(normalized_text)

        # Repetition is measured on the *raw* text so that deduplication
        # (which already removed consecutive copies) doesn't mask it.
        raw_lines = [l for l in raw_text.split("\n") if l.strip()]
        raw_n_lines = len(raw_lines)
        raw_freq = Counter(l.strip() for l in raw_lines)
        raw_dup = sum(c - 1 for c in raw_freq.values() if c > 1)
        rep_ratio = raw_dup / raw_n_lines if raw_n_lines else 0.0

        # Other metrics use normalized text
        norm_lines = [l for l in normalized_text.split("\n") if l.strip()]
        n_norm_lines = len(norm_lines)

        alpha_count = sum(1 for c in normalized_text if c.isalpha())
        alpha_ratio = alpha_count / n_chars if n_chars else 0.0

        short_lines_count = sum(1 for l in norm_lines if len(l.strip()) < _SHORT_LINE_LEN)
        short_ratio = short_lines_count / n_norm_lines if n_norm_lines else 0.0

        table_blocks = 0
        if blocks:
            table_blocks = sum(1 for b in blocks if b.type == "table")

        return QualityFlags(
            short_text=n_chars < _SHORT_TEXT_CHARS,
            very_short_text=n_chars < _VERY_SHORT_TEXT_CHARS,
            excessive_repetition=rep_ratio > _REPETITION_RATIO,
            mixed_language_possible=False,  # detected downstream by lingua
            low_alpha_ratio=alpha_ratio < _LOW_ALPHA_THRESHOLD,
            noisy_extraction=alpha_ratio < 0.3,
            mostly_template_text=rep_ratio > 0.6,
            too_many_short_lines=short_ratio > _SHORT_LINE_RATIO and n_norm_lines > 5,
            slide_like_format=source_format == "pptx",
            table_heavy_content=table_blocks >= 3,
        )

    # ── Metadata ────────────────────────────────────────────────────────────

    @staticmethod
    def _compute_metadata(
        raw_text: str,
        normalized_text: str,
        source_format: str,
        counters: _Counters,
        blocks: list[StructuredBlock] | None,
    ) -> NormalizationMetadata:
        return NormalizationMetadata(
            source_format=source_format,
            original_char_count=len(raw_text),
            normalized_char_count=len(normalized_text),
            original_line_count=raw_text.count("\n") + 1,
            normalized_line_count=normalized_text.count("\n") + 1,
            repeated_lines_removed=counters.repeated_lines_removed,
            repeated_paragraphs_removed=counters.repeated_paragraphs_removed,
            headers_footers_removed_count=counters.headers_footers_removed_count,
            hyphenation_fixes_count=counters.hyphenation_fixes_count,
            tables_detected=counters.tables_detected,
            slides_detected=counters.slides_detected,
        )
