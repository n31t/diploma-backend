"""
URL Detection service.

Orchestrates the full pipeline:
  NewspaperService → (optional TextCleaner) → AIDetectionModelService → history/limits

Replaces the previous Jina Reader + TextCleaner approach.
newspaper4k already returns clean plain text, so a heavy Markdown-stripping
step is no longer needed.  We still run a light normalisation pass (collapse
excess whitespace, strip control characters) before sending text to the model.
"""

from __future__ import annotations

import re
import time

from src.core.logging import get_logger
from src.dtos.ai_detection_dto import AIDetectionResultDTO, DetectionSource
from src.dtos.limits_dto import UserLimitDTO
from src.repositories.ai_detection_repository import AIDetectionRepository
from src.services.ml_model_service import AIDetectionModelService
from src.services.newspaper_service import NewspaperService

logger = get_logger(__name__)

# ── Light post-processing ─────────────────────────────────────────────────────

_CTRL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_MULTI_BLANK = re.compile(r"\n{3,}")


def _normalise(text: str) -> str:
    """
    Minimal cleanup of newspaper-extracted text.

    - Strip ASCII control characters (newspaper occasionally leaves them in).
    - Collapse 3+ consecutive blank lines to 2.
    - Strip leading/trailing whitespace.
    """
    text = _CTRL_CHARS.sub("", text)
    text = _MULTI_BLANK.sub("\n\n", text)
    return text.strip()


# ── Service ───────────────────────────────────────────────────────────────────

class URLDetectionService:
    """
    Application service for URL-based AI content detection.

    Pipeline
    --------
    1. Check user limits (daily / monthly).
    2. Download page + extract article text via NewspaperService.
    3. Light normalisation pass.
    4. Validate minimum text length.
    5. Run ML inference (AIDetectionModelService → ml-api microservice).
    6. Persist detection record + increment usage counters.
    7. Return AIDetectionResultDTO + updated UserLimitDTO.

    Dependencies
    ------------
    newspaper_service       — HTTP download + article extraction (I/O-bound)
    ml_model_service        — ML inference via internal HTTP microservice (I/O-bound)
    ai_detection_repository — PostgreSQL persistence (SQLAlchemy async)
    """

    def __init__(
        self,
        newspaper_service: NewspaperService,
        ml_model_service: AIDetectionModelService,
        ai_detection_repository: AIDetectionRepository,
    ) -> None:
        self._newspaper = newspaper_service
        self._model = ml_model_service
        self._repo = ai_detection_repository

    async def detect_from_url(
        self,
        url: str,
        user_id: str,
    ) -> tuple[AIDetectionResultDTO, UserLimitDTO]:
        """
        Run the full URL → detection pipeline for a user.

        Args:
            url:     Full HTTP/HTTPS URL of the article to analyse.
            user_id: Authenticated user's ULID.

        Returns:
            Tuple of (AIDetectionResultDTO, UserLimitDTO).

        Raises:
            ValueError:   Limit exceeded / URL invalid / too little text.
            RuntimeError: Network error or ML microservice unavailable.
        """
        start_time = time.time()
        logger.info("url_detection_start", url=url, user_id=user_id)

        # ── 1. Check limits ────────────────────────────────────────────────
        can_request, user_limit = await self._repo.can_make_request(user_id)
        if not can_request:
            logger.warning(
                "url_detection_limit_exceeded",
                user_id=user_id,
                daily_used=user_limit.daily_used,
                daily_limit=user_limit.daily_limit,
                monthly_used=user_limit.monthly_used,
                monthly_limit=user_limit.monthly_limit,
            )
            raise ValueError(
                f"Request limit exceeded. "
                f"Daily: {user_limit.daily_used}/{user_limit.daily_limit}, "
                f"Monthly: {user_limit.monthly_used}/{user_limit.monthly_limit}"
            )

        # ── 2. Fetch & extract article ─────────────────────────────────────
        # NewspaperService raises ValueError for bad URLs / no content,
        # RuntimeError for network failures.
        article = await self._newspaper.fetch_article(url)

        # ── 3. Normalise ───────────────────────────────────────────────────
        plain_text = _normalise(article.text)

        if not plain_text:
            raise ValueError(
                f"No readable text could be extracted from {url}."
            )

        # ── 4. Validate minimum length ─────────────────────────────────────
        if not self._model.validate_text(plain_text):
            raise ValueError(
                f"The page at {url} does not contain enough text for analysis "
                f"(minimum 50 characters required)."
            )

        # ── 5. ML inference ────────────────────────────────────────────────
        result, confidence = await self._model.detect_ai_text(plain_text)
        processing_time_ms = int((time.time() - start_time) * 1000)

        # ── 6. Persist ─────────────────────────────────────────────────────
        updated_limit = await self._repo.increment_usage(user_id)

        await self._repo.create_history_record(
            user_id=user_id,
            source="url",
            result=result.value,
            confidence=confidence,
            text_preview=plain_text[:500],
            text_length=len(plain_text),
            word_count=len(plain_text.split()),
            file_name=url,               # store the URL as "file_name" for history display
            processing_time_ms=processing_time_ms,
        )

        # ── 7. Build response DTOs ─────────────────────────────────────────
        detection_result = AIDetectionResultDTO(
            result=result,
            confidence=confidence,
            text_preview=plain_text[:200],
            source=DetectionSource.URL,
            file_name=url,
            metadata={
                "url": url,
                "page_title": article.title,
                "authors": article.authors,
                "publish_date": article.publish_date,
                "text_length": len(plain_text),
                "word_count": len(plain_text.split()),
                "processing_time_ms": processing_time_ms,
            },
        )

        logger.info(
            "url_detection_done",
            url=url,
            user_id=user_id,
            result=result.value,
            confidence=confidence,
            processing_time_ms=processing_time_ms,
        )

        return detection_result, UserLimitDTO.from_model(updated_limit)