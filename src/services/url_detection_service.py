"""
URL Detection service.

Orchestrates the full pipeline:
  Jina Reader → TextCleaner → AIDetectionModelService → history/limits
"""

import time

from src.core.logging import get_logger
from src.dtos.ai_detection_dto import AIDetectionResultDTO, DetectionSource
from src.dtos.limits_dto import UserLimitDTO
from src.repositories.ai_detection_repository import AIDetectionRepository
from src.services.jina_service import JinaReaderService
from src.services.ml_model_service import AIDetectionModelService
from src.services.text_cleaner_service import TextCleanerService

logger = get_logger(__name__)


class URLDetectionService:
    """
    Application service for URL-based AI content detection.

    Depends on:
    - JinaReaderService  (infrastructure: fetches page as Markdown)
    - TextCleanerService (domain: strips Markdown → plain text)
    - AIDetectionModelService (domain: ML inference)
    - AIDetectionRepository  (domain: limits + history persistence)
    """

    def __init__(
        self,
        jina_service: JinaReaderService,
        text_cleaner: TextCleanerService,
        ml_model_service: AIDetectionModelService,
        ai_detection_repository: AIDetectionRepository,
    ) -> None:
        self._jina = jina_service
        self._cleaner = text_cleaner
        self._model = ml_model_service
        self._repo = ai_detection_repository

    async def detect_from_url(
        self,
        url: str,
        user_id: str,
    ) -> tuple[AIDetectionResultDTO, UserLimitDTO]:
        """
        Run the full URL → detection pipeline for a user.

        Steps:
        1. Check user limits.
        2. Fetch page via Jina Reader.
        3. Clean raw Markdown → plain text.
        4. Validate text length.
        5. Run ML detection.
        6. Persist history + increment counters.
        7. Return result + updated limits.

        Args:
            url:     The target website URL.
            user_id: Authenticated user's ID.

        Returns:
            Tuple[AIDetectionResultDTO, UserLimitDTO]

        Raises:
            ValueError:   Limit exceeded / text too short / bad URL.
            RuntimeError: Jina is unreachable or ML model error.
        """
        start_time = time.time()
        logger.info("url_detection_start", url=url, user_id=user_id)

        # ── 1. limits ──────────────────────────────────────────────────────
        can_request, user_limit = await self._repo.can_make_request(user_id)
        if not can_request:
            logger.warning(
                "url_detection_limit_exceeded",
                user_id=user_id,
                daily_used=user_limit.daily_used,
                daily_limit=user_limit.daily_limit,
            )
            raise ValueError(
                f"Request limit exceeded. "
                f"Daily: {user_limit.daily_used}/{user_limit.daily_limit}, "
                f"Monthly: {user_limit.monthly_used}/{user_limit.monthly_limit}"
            )

        # ── 2. fetch ───────────────────────────────────────────────────────
        jina_result = await self._jina.fetch_markdown(url)

        # ── 3. clean ───────────────────────────────────────────────────────
        try:
            plain_text = self._cleaner.clean(jina_result.raw_markdown)

        except ValueError as exc:
            raise ValueError(f"Could not extract readable text from {url}: {exc}") from exc

        # ── 4. validate ────────────────────────────────────────────────────
        if not self._model.validate_text(plain_text):
            raise ValueError(
                f"The page at {url} does not contain enough text "
                f"for analysis (minimum 50 characters)."
            )

        # ── 5. detect ──────────────────────────────────────────────────────
        result, confidence = await self._model.detect_ai_text(plain_text)
        processing_time_ms = int((time.time() - start_time) * 1000)

        # ── 6. persist ─────────────────────────────────────────────────────
        updated_limit = await self._repo.increment_usage(user_id)

        await self._repo.create_history_record(
            user_id=user_id,
            source="url",
            result=result.value,
            confidence=confidence,
            text_preview=plain_text[:500],
            text_length=len(plain_text),
            word_count=len(plain_text.split()),
            file_name=url,          # store the URL as "file_name" for history
            processing_time_ms=processing_time_ms,
        )

        # ── 7. build DTOs ──────────────────────────────────────────────────
        detection_result = AIDetectionResultDTO(
            result=result,
            confidence=confidence,
            text_preview=plain_text[:200],
            source=DetectionSource.URL,   # reuse FILE variant (closest semantic)
            file_name=url,
            metadata={
                "url": url,
                "page_title": jina_result.title,
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