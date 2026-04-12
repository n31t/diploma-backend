"""
URL Detection service.

Orchestrates the full pipeline:
  NewspaperService → TextNormalizationService → AIDetectionModelService → history/limits
"""

from __future__ import annotations

import time
from dataclasses import asdict

from src.api.v1.schemas.detection_language import (
    DetectionLanguageContext,
    resolve_effective_language,
)
from src.core.logging import get_logger
from src.dtos.ai_detection_dto import AIDetectionResultDTO, DetectionSource
from src.dtos.limits_dto import UserLimitDTO
from src.repositories.ai_detection_repository import AIDetectionRepository
from src.services.ml_model_service import AIDetectionModelService
from src.services.newspaper_service import NewspaperService
from src.services.text_normalization_service import TextNormalizationService

logger = get_logger(__name__)


class URLDetectionService:
    """
    Application service for URL-based AI content detection.

    Pipeline
    --------
    1. Check user limits (daily / monthly).
    2. Download page + extract article text via NewspaperService.
    3. Normalize text via TextNormalizationService.
    4. Validate minimum text length.
    5. Resolve effective language from extracted text (if auto was requested).
    6. Run ML inference (AIDetectionModelService -> ml-api microservice).
    7. Persist detection record + increment usage counters.
    8. Return AIDetectionResultDTO + updated UserLimitDTO.
    """

    def __init__(
        self,
        newspaper_service: NewspaperService,
        ml_model_service: AIDetectionModelService,
        ai_detection_repository: AIDetectionRepository,
        normalization_service: TextNormalizationService,
    ) -> None:
        self._newspaper = newspaper_service
        self._model = ml_model_service
        self._repo = ai_detection_repository
        self._normalizer = normalization_service

    async def detect_from_url(
        self,
        url: str,
        user_id: str,
        *,
        language: DetectionLanguageContext,
    ) -> tuple[AIDetectionResultDTO, UserLimitDTO]:
        """Run the full URL -> detection pipeline for a user."""
        start_time = time.time()
        logger.info(
            "url_detection_start",
            url=url,
            user_id=user_id,
            language_requested=language.requested,
            language_effective=language.effective,
        )

        # 1. Check limits
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

        # 2. Fetch & extract article
        article = await self._newspaper.fetch_article(url)

        # 3. Normalize
        norm = self._normalizer.normalize(article.text, source_format="url")
        plain_text = norm.normalized_text

        if not plain_text:
            raise ValueError(
                f"No readable text could be extracted from {url}."
            )

        # 4. Validate minimum length
        if not self._model.validate_text(plain_text):
            raise ValueError(
                f"The page at {url} does not contain enough text for analysis "
                f"(minimum 50 characters required)."
            )

        # 5. Resolve language from extracted text (handles auto)
        language = resolve_effective_language(plain_text, language)

        logger.info(
            "url_language_resolved",
            url=url,
            language_requested=language.requested,
            language_effective=language.effective,
        )

        # 6. ML inference
        result, confidence = await self._model.detect_ai_text(
            plain_text, language=language.effective
        )
        processing_time_ms = int((time.time() - start_time) * 1000)

        # 7. Persist
        updated_limit = await self._repo.increment_usage(user_id)

        await self._repo.create_history_record(
            user_id=user_id,
            source="url",
            result=result.value,
            confidence=confidence,
            text_preview=norm.raw_text[:500],
            text_length=len(plain_text),
            word_count=len(plain_text.split()),
            file_name=url,
            processing_time_ms=processing_time_ms,
        )

        # 8. Build response DTOs
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
                "language_requested": language.requested,
                "language_effective": language.effective,
                "normalization": asdict(norm.metadata),
                "quality_flags": asdict(norm.quality_flags),
                "extraction_method": article.extraction_method,
                "extraction_fallback_used": article.fallback_used,
                "html_truncated": article.html_truncated,
                "extraction_rejection_notes": article.extraction_rejection_notes,
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
