"""
Detection language parsing for AI detection API.

Public API accepts ru, kk, or auto.
When auto is requested, the effective language is resolved from the text
using lingua-language-detector after text extraction (in the service layer).
Alias kz is accepted for Kazakh and normalized to kk.
"""

from dataclasses import dataclass
from typing import Literal

from lingua import Language, LanguageDetectorBuilder

from src.core.logging import get_logger

logger = get_logger(__name__)

DetectionLanguageInput = Literal["ru", "kk", "auto"]
DetectionLanguageRequested = Literal["ru", "kk", "auto"]
DetectionMlLanguage = Literal["ru", "kk"]

# Build detector once at module level — it's expensive to create
_detector = (
    LanguageDetectorBuilder
    .from_languages(Language.RUSSIAN, Language.KAZAKH)
    .build()
)


@dataclass(frozen=True)
class DetectionLanguageContext:
    """Resolved language for ML routing and what the client asked for."""

    effective: DetectionMlLanguage
    requested: DetectionLanguageRequested


def detect_language_from_text(text: str) -> DetectionMlLanguage:
    """
    Detect language from text using lingua.
    Returns "kk" for Kazakh, "ru" for everything else.

    Falls back to "ru" if detection fails (too little text, ambiguous, etc).
    """
    try:
        lang = _detector.detect_language_of(text[:2000])
        logger.info("language_auto_detected", detected=str(lang))
        if lang == Language.KAZAKH:
            return "kk"
        return "ru"
    except Exception as e:
        logger.warning("language_detection_failed", error=str(e), fallback="ru")
        return "ru"


def resolve_effective_language(
    text: str,
    context: DetectionLanguageContext,
) -> DetectionLanguageContext:
    """
    If the client requested auto, detect the language from the extracted text
    and return a new context with the resolved effective language.

    Call this in the service layer after text is available
    (i.e. after file extraction or URL scraping).

    Args:
        text:    The plain text to detect language from.
        context: The original language context from the request.

    Returns:
        A new DetectionLanguageContext with effective language resolved.
    """
    if context.requested != "auto":
        return context  # user explicitly chose ru or kk — respect it

    effective = detect_language_from_text(text)
    logger.info(
        "language_context_resolved",
        requested=context.requested,
        effective=effective,
    )
    return DetectionLanguageContext(effective=effective, requested="auto")


def context_from_api_language(lang: DetectionLanguageInput) -> DetectionLanguageContext:
    """
    Build routing context from a validated JSON field (ru | kk | auto).

    For auto, effective is set to "ru" as a temporary placeholder —
    call resolve_effective_language() in the service once text is available.
    """
    if lang == "auto":
        return DetectionLanguageContext(effective="ru", requested="auto")
    return DetectionLanguageContext(effective=lang, requested=lang)


def parse_detection_language(value: str | None) -> DetectionLanguageContext:
    """
    Parse and normalize language from JSON body or form field.

    Raises:
        ValueError: if the value is not one of ru, kk, kz, auto (or empty → auto).
    """
    raw = (value if value is not None else "auto").strip().lower()
    if raw in ("", "auto"):
        return DetectionLanguageContext(effective="ru", requested="auto")
    if raw == "ru":
        return DetectionLanguageContext(effective="ru", requested="ru")
    if raw in ("kk", "kz"):
        return DetectionLanguageContext(effective="kk", requested="kk")
    raise ValueError(
        "language must be one of: ru, kk, kz, auto. "
        f"Got {value!r}."
    )