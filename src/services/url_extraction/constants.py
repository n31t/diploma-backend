"""Centralized thresholds and selector lists for URL HTML extraction."""

from __future__ import annotations

# Must match historical newspaper_service cap: single download safety valve.
MAX_HTML_TEXT_LENGTH = 500_000

# Stricter than ML pipeline minimum (50 chars) — rejects nav crumbs / summaries.
MIN_EXTRACTION_CHARS = 200
MIN_EXTRACTION_WORDS = 40
MIN_MEANINGFUL_LINES = 3
MIN_LINE_LEN_FOR_COUNT = 25

# Reject mostly punctuation / symbols (navigation, icons as text).
MIN_ALPHA_RATIO = 0.32

# Same line repeated many times (menus, boilerplate).
MAX_REPEATED_SHORT_LINE = 8
SHORT_LINE_MAX_LEN = 80

# Tags to remove globally before root selection (generic).
NOISY_TAG_NAMES: frozenset[str] = frozenset(
    ("script", "style", "noscript", "svg", "footer", "header", "nav", "form", "iframe", "aside")
)

# CSS selectors tried in order for main content root (generic).
GENERIC_MAIN_ROOT_SELECTORS: tuple[str, ...] = (
    "article",
    "main",
    "[role='main']",
    ".post-content",
    ".article-content",
    ".entry-content",
    ".content",
    ".article-body",
    ".story-body",
    "#content",
    "#main-content",
)

# Blocks to strip inside chosen root (generic).
GENERIC_REMOVE_SELECTORS: tuple[str, ...] = (
    "nav",
    "header",
    "footer",
    "aside",
    ".sidebar",
    ".related",
    ".promo",
    ".share",
    ".social",
    ".comments",
    "#comments",
    ".advertisement",
    ".ad",
    ".toc",
    "table",
)

# Wikipedia: noise to remove inside content area.
WIKIPEDIA_REMOVE_SELECTORS: tuple[str, ...] = (
    "table",
    ".infobox",
    ".navbox",
    ".vertical-navbox",
    ".toc",
    ".reflist",
    ".reference",
    ".references",
    ".mw-editsection",
    ".metadata",
    ".sidebar",
    ".thumb",
    ".gallery",
    ".mbox",
    ".noprint",
    "#catlinks",
)

# Tags whose text we collect for body extraction.
CONTENT_TEXT_TAGS: frozenset[str] = frozenset(
    ("p", "li", "h2", "h3", "blockquote")
)
