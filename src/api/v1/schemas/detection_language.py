"""
Detection language parsing for AI detection API.

Public API accepts ru, kk, or auto (auto routes to Russian ML stack).
Alias kz is accepted for Kazakh and normalized to kk.
"""

from dataclasses import dataclass
from typing import Literal

DetectionLanguageInput = Literal["ru", "kk", "auto"]
DetectionLanguageRequested = Literal["ru", "kk", "auto"]
DetectionMlLanguage = Literal["ru", "kk"]


@dataclass(frozen=True)
class DetectionLanguageContext:
    """Resolved language for ML routing and what the client asked for."""

    effective: DetectionMlLanguage
    requested: DetectionLanguageRequested


def context_from_api_language(lang: DetectionLanguageInput) -> DetectionLanguageContext:
    """Build routing context from a validated JSON field (ru | kk | auto)."""
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
