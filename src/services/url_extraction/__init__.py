"""HTML article extraction helpers for URL-based AI detection (BeautifulSoup fallbacks)."""

from src.services.url_extraction.bs4_generic import extract_generic_text
from src.services.url_extraction.bs4_wikipedia import extract_wikipedia_text
from src.services.url_extraction.constants import MAX_HTML_TEXT_LENGTH
from src.services.url_extraction.domain import is_wikipedia_host, parsed_host
from src.services.url_extraction.quality import ExtractionQualityResult, evaluate_text_quality

__all__ = [
    "MAX_HTML_TEXT_LENGTH",
    "ExtractionQualityResult",
    "evaluate_text_quality",
    "extract_generic_text",
    "extract_wikipedia_text",
    "is_wikipedia_host",
    "parsed_host",
]
