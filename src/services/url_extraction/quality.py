"""Heuristic quality gate for extracted plain text (before ML min-length check)."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from src.services.url_extraction.constants import (
    MAX_REPEATED_SHORT_LINE,
    MIN_ALPHA_RATIO,
    MIN_EXTRACTION_CHARS,
    MIN_EXTRACTION_WORDS,
    MIN_LINE_LEN_FOR_COUNT,
    MIN_MEANINGFUL_LINES,
    SHORT_LINE_MAX_LEN,
)

_WORD_RE = re.compile(r"\w+", re.UNICODE)


@dataclass(frozen=True)
class ExtractionQualityResult:
    accepted: bool
    rejection_reason: str | None
    char_count: int
    word_count: int
    paragraph_count: int
    alpha_ratio: float


def _count_alpha_ratio(text: str) -> float:
    if not text:
        return 0.0
    letters = sum(1 for c in text if c.isalpha())
    return letters / max(len(text), 1)


def _meaningful_lines(text: str) -> int:
    return sum(
        1
        for line in text.splitlines()
        if len(line.strip()) >= MIN_LINE_LEN_FOR_COUNT
    )


def _worst_repetition(text: str) -> int:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return 0
    short = [ln for ln in lines if len(ln) <= SHORT_LINE_MAX_LEN]
    if not short:
        return 0
    return max(Counter(short).values(), default=0)


def evaluate_text_quality(text: str) -> ExtractionQualityResult:
    """
    Return whether extracted text is substantial enough for downstream ML.

    This is stricter than the ML service's 50-character minimum.
    """
    stripped = (text or "").strip()
    char_count = len(stripped)
    words = _WORD_RE.findall(stripped)
    word_count = len(words)
    paragraph_count = _meaningful_lines(stripped)
    alpha_ratio = _count_alpha_ratio(stripped)

    if char_count < MIN_EXTRACTION_CHARS:
        return ExtractionQualityResult(
            False,
            "too_few_chars",
            char_count,
            word_count,
            paragraph_count,
            alpha_ratio,
        )
    if word_count < MIN_EXTRACTION_WORDS:
        return ExtractionQualityResult(
            False,
            "too_few_words",
            char_count,
            word_count,
            paragraph_count,
            alpha_ratio,
        )
    if paragraph_count < MIN_MEANINGFUL_LINES:
        return ExtractionQualityResult(
            False,
            "too_few_meaningful_lines",
            char_count,
            word_count,
            paragraph_count,
            alpha_ratio,
        )
    if alpha_ratio < MIN_ALPHA_RATIO:
        return ExtractionQualityResult(
            False,
            "low_alpha_ratio",
            char_count,
            word_count,
            paragraph_count,
            alpha_ratio,
        )

    rep = _worst_repetition(stripped)
    if rep >= MAX_REPEATED_SHORT_LINE:
        return ExtractionQualityResult(
            False,
            "excessive_repetition",
            char_count,
            word_count,
            paragraph_count,
            alpha_ratio,
        )

    return ExtractionQualityResult(
        True,
        None,
        char_count,
        word_count,
        paragraph_count,
        alpha_ratio,
    )
