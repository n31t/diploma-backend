"""
Newspaper service for fetching and extracting article text from URLs.

Uses newspaper4k (async-native fork of newspaper3k) to download web pages,
extract the main article body, and strip all markup — leaving clean plain text
suitable for the ML detection pipeline.

Supports Russian and Kazakh content out of the box via newspaper's built-in
language heuristics and lxml-based HTML parsing.
"""

from __future__ import annotations

import asyncio
from urllib.parse import urlparse

import httpx
from newspaper import Article, Config as NewspaperConfig

from src.core.logging import get_logger
from src.dtos.ai_detection_dto import NewspaperFetchResultDTO

logger = get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

REQUEST_TIMEOUT = 30          # seconds for the HTTP download
MAX_CONTENT_LENGTH = 500_000  # 500 KB raw HTML cap (safety valve)
MIN_TEXT_LENGTH = 50          # characters; enforced upstream, but logged here
DEFAULT_LANGUAGE = "ru"       # primary language hint for newspaper parser


def _build_newspaper_config() -> NewspaperConfig:
    """Return a shared newspaper Config tuned for our use-case."""
    cfg = NewspaperConfig()
    cfg.browser_user_agent = (
        "Mozilla/5.0 (compatible; AIDetector/1.0; +https://example.com)"
    )
    cfg.request_timeout = REQUEST_TIMEOUT
    cfg.fetch_images = False       # we only need text
    cfg.memoize_articles = False   # stateless — no caching between requests
    cfg.language = DEFAULT_LANGUAGE
    return cfg


_NEWSPAPER_CONFIG = _build_newspaper_config()


class NewspaperService:
    """
    Service that downloads a web page and extracts its article text.

    Newspaper handles:
    - HTML download (via requests internally; we wrap with httpx for async)
    - Boilerplate removal (nav bars, ads, footers, …)
    - Language detection and multi-language NLP (ru / kk supported)
    - Metadata extraction (title, authors, publish date)

    We run the CPU-bound newspaper parse step in a thread-pool executor
    so we do not block the asyncio event loop.
    """

    async def fetch_article(self, url: str) -> NewspaperFetchResultDTO:
        """
        Download *url* and return its extracted article text and metadata.

        Args:
            url: Full HTTP/HTTPS URL of the target page.

        Returns:
            NewspaperFetchResultDTO with plain text and metadata.

        Raises:
            ValueError:   URL is invalid, page has no readable content, or
                          extracted text is below the minimum length.
            RuntimeError: Network error or unexpected parsing failure.
        """
        self._validate_url(url)
        logger.info("newspaper_fetch_start", url=url)

        # ── 1. Download HTML via httpx (async) ────────────────────────────
        raw_html = await self._download_html(url)

        # ── 2. Parse article in thread pool (CPU-bound) ───────────────────
        try:
            dto = await asyncio.get_event_loop().run_in_executor(
                None, self._parse_article, url, raw_html
            )
        except Exception as exc:
            logger.error(
                "newspaper_parse_error",
                url=url,
                error=str(exc),
                exc_info=True,
            )
            raise RuntimeError(
                f"Failed to parse article content from {url}: {exc}"
            ) from exc

        logger.info(
            "newspaper_fetch_done",
            url=url,
            text_length=len(dto.text),
            title=dto.title,
        )
        return dto

    # ── private helpers ───────────────────────────────────────────────────────

    async def _download_html(self, url: str) -> str:
        """
        Fetch raw HTML for *url* using httpx.

        Returns raw HTML string.

        Raises:
            RuntimeError on network / HTTP errors.
            ValueError   if the server returns an empty body.
        """
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (compatible; AIDetector/1.0; +https://example.com)"
            ),
            "Accept-Language": "ru,kk;q=0.9,en;q=0.8",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }

        try:
            async with httpx.AsyncClient(
                timeout=REQUEST_TIMEOUT,
                follow_redirects=True,
                headers=headers,
            ) as client:
                response = await client.get(url)
                response.raise_for_status()
                # Read up to MAX_CONTENT_LENGTH bytes
                content = response.text[:MAX_CONTENT_LENGTH]

        except httpx.HTTPStatusError as exc:
            logger.error(
                "newspaper_http_error",
                url=url,
                status=exc.response.status_code,
            )
            raise RuntimeError(
                f"HTTP {exc.response.status_code} while fetching {url}"
            ) from exc
        except httpx.RequestError as exc:
            logger.error("newspaper_request_error", url=url, error=str(exc))
            raise RuntimeError(
                f"Network error while fetching {url}: {exc}"
            ) from exc

        if not content or not content.strip():
            raise ValueError(f"Server returned an empty response for {url}")

        return content

    @staticmethod
    def _parse_article(url: str, html: str) -> NewspaperFetchResultDTO:
        """
        Run newspaper's NLP pipeline on pre-downloaded HTML.

        This is a synchronous, CPU-bound operation — always call it via
        run_in_executor to avoid blocking the event loop.

        Returns:
            NewspaperFetchResultDTO

        Raises:
            ValueError if no text could be extracted.
        """
        article = Article(url, config=_NEWSPAPER_CONFIG)
        article.download(input_html=html)
        article.parse()

        text: str = (article.text or "").strip()
        title: str | None = article.title or None
        authors: list[str] = article.authors or []
        publish_date = article.publish_date  # datetime | None

        if not text:
            # Fallback: try meta description + summary
            article.nlp()
            text = (article.summary or "").strip()

        if not text:
            raise ValueError(
                f"Newspaper could not extract any readable text from {url}. "
                "The page may be JavaScript-rendered, paywalled, or empty."
            )

        logger.debug(
            "newspaper_parsed",
            url=url,
            text_length=len(text),
            title=title,
            authors=authors,
        )

        return NewspaperFetchResultDTO(
            text=text,
            url=url,
            title=title,
            authors=authors,
            publish_date=str(publish_date) if publish_date else None,
        )

    @staticmethod
    def _validate_url(url: str) -> None:
        """
        Raise ValueError if *url* is clearly invalid.

        Accepts only http and https schemes with a non-empty host.
        """
        try:
            parsed = urlparse(url)
        except Exception as exc:
            raise ValueError(f"Cannot parse URL: {url!r}") from exc

        if parsed.scheme not in ("http", "https"):
            raise ValueError(
                f"Only http/https URLs are supported, got scheme: {parsed.scheme!r}"
            )
        if not parsed.netloc:
            raise ValueError(f"URL has no host: {url!r}")