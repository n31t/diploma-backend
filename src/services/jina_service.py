"""
Jina service for fetching website content as Markdown.

Uses Jina's r.jina.ai reader API which converts any URL to clean Markdown.
No API key required for basic usage.
"""

import re
import urllib.request
import urllib.error
from urllib.parse import urlparse

from src.core.logging import get_logger
from src.dtos.ai_detection_dto import JinaFetchResultDTO

logger = get_logger(__name__)

JINA_BASE_URL = "https://r.jina.ai/"
REQUEST_TIMEOUT = 30  # seconds
MAX_CONTENT_LENGTH = 500_000  # 500 KB of raw text max


class JinaReaderService:
    """
    Service that fetches website content via Jina Reader API
    and returns raw Markdown for further processing.
    """

    async def fetch_markdown(self, url: str) -> JinaFetchResultDTO:
        """
        Fetch a website's content as Markdown via Jina Reader.

        Args:
            url: The target website URL.

        Returns:
            JinaFetchResultDTO with raw markdown and metadata.

        Raises:
            ValueError: If the URL is invalid or the site returned no content.
            RuntimeError: If Jina Reader is unreachable or returns an error.
        """
        self._validate_url(url)

        jina_url = f"{JINA_BASE_URL}{url}"
        logger.info("jina_fetch_start", url=url, jina_url=jina_url)

        try:
            req = urllib.request.Request(
                jina_url,
                headers={
                    "Accept": "text/plain",
                    "User-Agent": "Mozilla/5.0 (compatible; AIDetector/1.0)",
                },
            )
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as response:
                raw_bytes = response.read(MAX_CONTENT_LENGTH)
                markdown = raw_bytes.decode("utf-8", errors="replace")

        except urllib.error.HTTPError as exc:
            logger.error(
                "jina_http_error", url=url, status=exc.code, reason=exc.reason
            )
            raise RuntimeError(
                f"Jina Reader returned HTTP {exc.code} for URL: {url}"
            ) from exc
        except urllib.error.URLError as exc:
            logger.error("jina_url_error", url=url, error=str(exc.reason))
            raise RuntimeError(
                f"Failed to reach Jina Reader: {exc.reason}"
            ) from exc
        except Exception as exc:
            logger.error("jina_unexpected_error", url=url, error=str(exc), exc_info=True)
            raise RuntimeError(
                f"Unexpected error while fetching URL: {exc}"
            ) from exc

        if not markdown or not markdown.strip():
            raise ValueError(f"Jina Reader returned empty content for URL: {url}")

        title = self._extract_title(markdown)

        logger.info(
            "jina_fetch_done",
            url=url,
            content_length=len(markdown),
            title=title,
        )

        return JinaFetchResultDTO(raw_markdown=markdown, url=url, title=title)

    # ── private helpers ────────────────────────────────────────────────────

    @staticmethod
    def _validate_url(url: str) -> None:
        """Raise ValueError if the URL is clearly invalid."""
        try:
            parsed = urlparse(url)
        except Exception:
            raise ValueError(f"Cannot parse URL: {url}")

        if parsed.scheme not in ("http", "https"):
            raise ValueError(
                f"Only http/https URLs are supported, got: '{parsed.scheme}'"
            )
        if not parsed.netloc:
            raise ValueError(f"URL has no host: {url}")

    @staticmethod
    def _extract_title(markdown: str) -> str | None:
        """Try to pull the page title from the first H1 line."""
        for line in markdown.splitlines():
            stripped = line.strip()
            if stripped.startswith("# "):
                return stripped[2:].strip()
        return None