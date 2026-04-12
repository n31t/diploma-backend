"""
Newspaper service for fetching and extracting article text from URLs.

Primary: newspaper4k. Fallback: BeautifulSoup generic + Wikipedia-specific paths.
Uses a single httpx download; all parsers run in a thread pool.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx
from newspaper import Article, Config as NewspaperConfig

from src.core.logging import get_logger
from src.dtos.ai_detection_dto import ExtractionMethod, NewspaperFetchResultDTO
from src.services.url_extraction.bs4_generic import extract_generic_text
from src.services.url_extraction.bs4_wikipedia import extract_wikipedia_text
from src.services.url_extraction.constants import MAX_HTML_TEXT_LENGTH
from src.services.url_extraction.domain import is_wikipedia_host, parsed_host
from src.services.url_extraction.quality import ExtractionQualityResult, evaluate_text_quality

logger = get_logger(__name__)

REQUEST_TIMEOUT = 30
DEFAULT_LANGUAGE = "ru"


def _build_newspaper_config() -> NewspaperConfig:
    cfg = NewspaperConfig()
    cfg.browser_user_agent = (
        "Mozilla/5.0 (compatible; AIDetector/1.0; +https://example.com)"
    )
    cfg.request_timeout = REQUEST_TIMEOUT
    cfg.fetch_images = False
    cfg.memoize_articles = False
    cfg.language = DEFAULT_LANGUAGE
    return cfg


_NEWSPAPER_CONFIG = _build_newspaper_config()


@dataclass(frozen=True)
class DownloadedHtml:
    """Result of a single HTTP GET for extraction."""

    content: str
    truncated: bool
    original_text_length: int


class NewspaperService:
    """
    Downloads HTML once, then runs extraction strategies (newspaper + BS4 fallbacks).
    """

    async def fetch_article(self, url: str) -> NewspaperFetchResultDTO:
        """
        Download *url* and return extracted article text and metadata.

        Raises:
            ValueError: URL invalid or empty HTTP body.
            RuntimeError: Network error or all extractors failed quality gates.
        """
        self._validate_url(url)
        t0 = time.perf_counter()
        host = parsed_host(url)
        logger.info("extraction_pipeline_started", url=url, host=host)

        downloaded = await self._download_html(url)
        html = downloaded.content
        html_truncated = downloaded.truncated
        html_len = len(html)

        logger.info(
            "html_downloaded",
            url=url,
            host=host,
            html_length=html_len,
            html_truncated=html_truncated,
            original_text_length=downloaded.original_text_length,
        )
        if html_truncated:
            logger.warning(
                "html_truncated",
                url=url,
                host=host,
                html_length=html_len,
                max_length=MAX_HTML_TEXT_LENGTH,
            )

        loop = asyncio.get_event_loop()
        wikipedia = is_wikipedia_host(host)
        notes: list[str] = []

        def log_quality_eval(q: ExtractionQualityResult, extractor: str) -> None:
            logger.info(
                "extraction_quality_evaluated",
                url=url,
                host=host,
                extractor=extractor,
                text_length=q.char_count,
                word_count=q.word_count,
                paragraph_count=q.paragraph_count,
                alpha_ratio=round(q.alpha_ratio, 4),
                accepted=q.accepted,
                rejection_reason=q.rejection_reason,
            )

        def complete_success(
            text: str,
            title: str | None,
            authors: list[str],
            publish_date: str | None,
            method: ExtractionMethod,
            fallback_used: bool,
            quality: ExtractionQualityResult,
            *,
            strategy_success_event: str,
        ) -> NewspaperFetchResultDTO:
            log_quality_eval(quality, method)
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            logger.info(
                strategy_success_event,
                url=url,
                host=host,
                text_length=len(text),
            )
            logger.info(
                "extraction_pipeline_succeeded",
                url=url,
                host=host,
                extractor=method,
                fallback_used=fallback_used,
                text_length=len(text),
                word_count=quality.word_count,
                paragraph_count=quality.paragraph_count,
                html_truncated=html_truncated,
                html_length=html_len,
                processing_time_ms=elapsed_ms,
            )
            return NewspaperFetchResultDTO(
                text=text,
                url=url,
                title=title,
                authors=authors,
                publish_date=publish_date,
                extraction_method=method,
                fallback_used=fallback_used,
                html_truncated=html_truncated,
                extraction_rejection_notes=notes,
            )

        # ── Wikipedia: BS4 Wikipedia → newspaper → BS4 generic ─────────────
        if wikipedia:
            logger.info("bs4_wikipedia_started", url=url, host=host)
            wiki_text: str = ""
            wiki_title: str | None = None
            try:
                wiki_text, wiki_title = await loop.run_in_executor(
                    None, extract_wikipedia_text, html, url
                )
            except Exception as exc:
                logger.error(
                    "bs4_wikipedia_failed",
                    url=url,
                    host=host,
                    error=str(exc),
                    exc_info=True,
                )
                notes.append(f"wikipedia_bs4_exception:{exc!s}")
            else:
                if wiki_text.strip():
                    qr = evaluate_text_quality(wiki_text)
                    if qr.accepted:
                        return complete_success(
                            wiki_text,
                            wiki_title,
                            [],
                            None,
                            "bs4_wikipedia",
                            False,
                            qr,
                            strategy_success_event="bs4_wikipedia_succeeded",
                        )
                    log_quality_eval(qr, "bs4_wikipedia")
                    notes.append(f"wikipedia_bs4_rejected:{qr.rejection_reason}")

            logger.info("newspaper_extraction_started", url=url, host=host)
            np_dto: NewspaperFetchResultDTO | None = None
            try:
                np_dto = await loop.run_in_executor(
                    None, self._parse_with_newspaper, url, html
                )
            except Exception as exc:
                logger.error(
                    "newspaper_extraction_failed",
                    url=url,
                    host=host,
                    error=str(exc),
                    exc_info=True,
                )
                notes.append(f"newspaper_exception:{exc!s}")
            else:
                qr = evaluate_text_quality(np_dto.text)
                if qr.accepted:
                    return complete_success(
                        np_dto.text,
                        np_dto.title,
                        np_dto.authors,
                        np_dto.publish_date,
                        "newspaper",
                        True,
                        qr,
                        strategy_success_event="newspaper_extraction_succeeded",
                    )
                log_quality_eval(qr, "newspaper")
                notes.append(f"newspaper_rejected:{qr.rejection_reason}")
                logger.info(
                    "newspaper_extraction_rejected",
                    url=url,
                    host=host,
                    extractor="newspaper",
                    rejection_reason=qr.rejection_reason,
                )

            logger.info("bs4_generic_started", url=url, host=host)
            try:
                gen_text, gen_title = await loop.run_in_executor(
                    None, extract_generic_text, html, url
                )
            except Exception as exc:
                logger.error(
                    "bs4_generic_failed",
                    url=url,
                    host=host,
                    error=str(exc),
                    exc_info=True,
                )
                notes.append(f"generic_bs4_exception:{exc!s}")
            else:
                if gen_text.strip():
                    qr = evaluate_text_quality(gen_text)
                    if qr.accepted:
                        return complete_success(
                            gen_text,
                            gen_title,
                            [],
                            None,
                            "bs4_generic",
                            True,
                            qr,
                            strategy_success_event="bs4_generic_succeeded",
                        )
                    log_quality_eval(qr, "bs4_generic")
                    notes.append(f"generic_bs4_rejected:{qr.rejection_reason}")

            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            logger.error(
                "extraction_pipeline_failed",
                url=url,
                host=host,
                html_truncated=html_truncated,
                processing_time_ms=elapsed_ms,
                notes=notes,
            )
            raise RuntimeError(
                f"Could not extract acceptable text from {url} after all strategies."
            )

        # ── General: newspaper → BS4 generic ──────────────────────────────
        logger.info("newspaper_extraction_started", url=url, host=host)
        try:
            np_dto = await loop.run_in_executor(
                None, self._parse_with_newspaper, url, html
            )
        except Exception as exc:
            logger.error(
                "newspaper_extraction_failed",
                url=url,
                host=host,
                error=str(exc),
                exc_info=True,
            )
            notes.append(f"newspaper_exception:{exc!s}")
        else:
            qr = evaluate_text_quality(np_dto.text)
            if qr.accepted:
                return complete_success(
                    np_dto.text,
                    np_dto.title,
                    np_dto.authors,
                    np_dto.publish_date,
                    "newspaper",
                    False,
                    qr,
                    strategy_success_event="newspaper_extraction_succeeded",
                )
            log_quality_eval(qr, "newspaper")
            notes.append(f"newspaper_rejected:{qr.rejection_reason}")
            logger.info(
                "newspaper_extraction_rejected",
                url=url,
                host=host,
                extractor="newspaper",
                rejection_reason=qr.rejection_reason,
            )

        logger.info("bs4_generic_started", url=url, host=host)
        try:
            gen_text, gen_title = await loop.run_in_executor(
                None, extract_generic_text, html, url
            )
        except Exception as exc:
            logger.error(
                "bs4_generic_failed",
                url=url,
                host=host,
                error=str(exc),
                exc_info=True,
            )
            notes.append(f"generic_bs4_exception:{exc!s}")
        else:
            if gen_text.strip():
                qr = evaluate_text_quality(gen_text)
                if qr.accepted:
                    return complete_success(
                        gen_text,
                        gen_title,
                        [],
                        None,
                        "bs4_generic",
                        True,
                        qr,
                        strategy_success_event="bs4_generic_succeeded",
                    )
                log_quality_eval(qr, "bs4_generic")
                notes.append(f"generic_bs4_rejected:{qr.rejection_reason}")

        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        logger.error(
            "extraction_pipeline_failed",
            url=url,
            host=host,
            html_truncated=html_truncated,
            processing_time_ms=elapsed_ms,
            notes=notes,
        )
        raise RuntimeError(
            f"Could not extract acceptable text from {url} after all strategies."
        )

    async def _download_html(self, url: str) -> DownloadedHtml:
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
                full_text = response.text
                original_len = len(full_text)
                truncated = original_len > MAX_HTML_TEXT_LENGTH
                content = full_text[:MAX_HTML_TEXT_LENGTH]

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

        return DownloadedHtml(
            content=content,
            truncated=truncated,
            original_text_length=original_len,
        )

    @staticmethod
    def _parse_with_newspaper(url: str, html: str) -> NewspaperFetchResultDTO:
        """Run newspaper4k on downloaded HTML (sync; call via executor)."""
        article = Article(url, config=_NEWSPAPER_CONFIG)
        article.download(input_html=html)
        article.parse()

        text = (article.text or "").strip()
        title: str | None = article.title or None
        authors: list[str] = article.authors or []
        publish_date = article.publish_date

        if not text:
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
            extraction_method="newspaper",
            fallback_used=False,
            html_truncated=False,
            extraction_rejection_notes=[],
        )

    @staticmethod
    def _validate_url(url: str) -> None:
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
