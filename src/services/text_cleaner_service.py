"""
Text cleaner service.

Converts raw Markdown (as returned by Jina Reader) into clean plain text
suitable for the ML detection model.

No external dependencies — only Python stdlib + regex.
"""

import re

from src.core.logging import get_logger

logger = get_logger(__name__)


class TextCleanerService:
    """
    Strips Markdown markup and noise, leaving only human-readable plain text.

    Rules (applied in order):
    1.  Remove YAML / front-matter blocks.
    2.  Remove fenced code blocks (``` ... ```).
    3.  Remove inline code (`...`).
    4.  Remove HTML tags.
    5.  Replace Markdown links  [text](url)  →  text.
    6.  Replace Markdown images ![alt](url)  →  alt  (or empty).
    7.  Remove heading hashes  (#, ##, …).
    8.  Remove bold/italic markers (**, __, *, _).
    9.  Remove blockquote markers (>).
    10. Remove horizontal rules (---, ***, ___).
    11. Remove Markdown table pipes and dashes.
    12. Collapse multiple blank lines → single blank line.
    13. Strip leading/trailing whitespace on each line.
    14. Remove lines that contain only URLs or punctuation.
    15. Final strip.
    """

    # ── compiled patterns (class-level, built once) ────────────────────────

    _FRONT_MATTER = re.compile(r"^---[\s\S]*?---\n?", re.MULTILINE)
    _FENCED_CODE  = re.compile(r"```[\s\S]*?```", re.MULTILINE)
    _INLINE_CODE  = re.compile(r"`[^`]+`")
    _HTML_TAG     = re.compile(r"<[^>]+>", re.DOTALL)
    _MD_LINK      = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
    _HEADING      = re.compile(r"^#{1,6}\s+", re.MULTILINE)
    _BOLD_ITALIC  = re.compile(r"(\*{1,3}|_{1,3})(.*?)\1", re.DOTALL)
    _BLOCKQUOTE   = re.compile(r"^>\s?", re.MULTILINE)
    _HR           = re.compile(r"^(\s*[-*_]){3,}\s*$", re.MULTILINE)
    _TABLE_ROW    = re.compile(r"^\|.*\|$", re.MULTILINE)
    _TABLE_SEP    = re.compile(r"^[\|\s\-:]+$", re.MULTILINE)
    _MULTI_BLANK  = re.compile(r"\n{3,}")
    _ONLY_URL     = re.compile(
        r"^\s*(https?://\S+|www\.\S+)\s*$", re.MULTILINE
    )
    _ONLY_PUNCT   = re.compile(r"^\s*[\W_]+\s*$", re.MULTILINE)
    # Jina sometimes adds metadata lines like "Source: …" at the top
    _JINA_META    = re.compile(
        r"^(Source|URL|Title|Description|Published|Author|Date|Tags):\s.*$",
        re.MULTILINE | re.IGNORECASE,
    )

    def clean(self, markdown: str) -> str:
        """
        Convert Markdown text to clean plain text.

        Args:
            markdown: Raw Markdown string (e.g. from Jina Reader).

        Returns:
            Plain text with all Markdown markup removed.

        Raises:
            ValueError: If the cleaned text is empty.
        """
        text = markdown

        text = self._FRONT_MATTER.sub("", text)
        text = self._FENCED_CODE.sub("", text)
        text = self._INLINE_CODE.sub("", text)
        text = self._HTML_TAG.sub("", text)

        # Markdown links/images: keep only the visible label
        text = self._MD_LINK.sub(lambda m: m.group(1), text)

        text = self._HEADING.sub("", text)

        # Bold / italic: keep inner text
        text = self._BOLD_ITALIC.sub(lambda m: m.group(2), text)

        text = self._BLOCKQUOTE.sub("", text)
        text = self._HR.sub("", text)
        text = self._TABLE_ROW.sub("", text)
        text = self._TABLE_SEP.sub("", text)
        text = self._JINA_META.sub("", text)
        text = self._ONLY_URL.sub("", text)
        text = self._ONLY_PUNCT.sub("", text)

        # Normalise whitespace
        lines = [line.strip() for line in text.splitlines()]
        text = "\n".join(lines)
        text = self._MULTI_BLANK.sub("\n\n", text)
        text = text.strip()

        if not text:
            raise ValueError("No readable text remained after cleaning.")

        logger.debug("text_cleaned", char_count=len(text), word_count=len(text.split()))
        return text