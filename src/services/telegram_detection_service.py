"""
Telegram Detection Service — thin façade over AIDetectionService / URLDetectionService.

Responsibility: translate Telegram-specific inputs (raw bytes + file_name
from the Telegram client) into calls on domain services, and return
structured results that the bot handler can render into messages.

This keeps all business logic in domain services and all Telegram
transport concerns in TelegramBotService.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from src.api.v1.schemas.detection_language import DetectionLanguageContext
from src.core.logging import get_logger
from src.dtos.ai_detection_dto import AIDetectionResultDTO, DetectionResult
from src.dtos.limits_dto import UserLimitDTO
from src.services.ai_detection_service import AIDetectionService
from src.services.url_detection_service import URLDetectionService

logger = get_logger(__name__)

DetectionKind = Literal["text", "file", "image", "url"]


@dataclass
class TelegramDetectionResult:
    """
    Result returned to the Telegram bot handler.

    Contains everything the handler needs to compose a reply —
    no business objects leak into the transport layer.
    """
    result: DetectionResult
    confidence: float
    processing_time_ms: int
    word_count: int
    source_label: str          # legacy display hint; prefer detection_kind + i18n
    file_name: str | None
    daily_remaining: int
    monthly_remaining: int
    language_requested: str
    language_effective: str
    detection_kind: DetectionKind


class TelegramDetectionService:
    """
    Application-layer service that bridges Telegram transport ↔ domain.

    Accepts only primitive types (str, bytes) so it stays independent
    of aiogram and can be unit-tested without a running bot.
    """

    def __init__(
        self,
        ai_detection_service: AIDetectionService,
        url_detection_service: URLDetectionService,
    ) -> None:
        self._ai_detection = ai_detection_service
        self._url_detection = url_detection_service

    async def detect_text(
        self,
        text: str,
        user_id: str,
        *,
        language: DetectionLanguageContext,
    ) -> TelegramDetectionResult:
        """
        Run AI detection on a plain-text string.

        Raises:
            ValueError: text too short / limits exceeded (re-raised from domain).
        """
        logger.info("telegram_detect_text", user_id=user_id, text_length=len(text))

        result_dto, limits_dto = await self._ai_detection.detect_from_text(
            text=text,
            user_id=user_id,
            language=language,
        )

        return self._build_result(
            result_dto=result_dto,
            limits_dto=limits_dto,
            source_label="text",
            detection_kind="text",
        )

    async def detect_file(
        self,
        file_bytes: bytes,
        file_name: str,
        content_type: str,
        user_id: str,
        *,
        language: DetectionLanguageContext,
    ) -> TelegramDetectionResult:
        """
        Run AI detection on a file uploaded via Telegram.

        Raises:
            ValueError:   File too large / wrong extension / text too short /
                          limits exceeded.
            RuntimeError: Gemini extraction failed.
        """
        logger.info(
            "telegram_detect_file",
            user_id=user_id,
            file_name=file_name,
            file_size=len(file_bytes),
        )

        result_dto, limits_dto = await self._ai_detection.detect_from_file(
            file_content=file_bytes,
            file_name=file_name,
            content_type=content_type,
            user_id=user_id,
            language=language,
        )

        return self._build_result(
            result_dto=result_dto,
            limits_dto=limits_dto,
            source_label="file",
            detection_kind="file",
        )

    async def detect_image(
        self,
        image_bytes: bytes,
        file_name: str,
        user_id: str,
        *,
        language: DetectionLanguageContext,
    ) -> TelegramDetectionResult:
        """
        Run AI detection on a photo sent via Telegram.

        Telegram compresses photos and does not expose a MIME type, so we
        always treat them as image/jpeg with a synthetic filename.
        """
        logger.info(
            "telegram_detect_image",
            user_id=user_id,
            file_name=file_name,
            file_size=len(image_bytes),
        )

        result_dto, limits_dto = await self._ai_detection.detect_from_file(
            file_content=image_bytes,
            file_name=file_name,
            content_type="image/jpeg",
            user_id=user_id,
            language=language,
        )

        return self._build_result(
            result_dto=result_dto,
            limits_dto=limits_dto,
            source_label="image",
            detection_kind="image",
        )

    async def detect_url(
        self,
        url: str,
        user_id: str,
        *,
        language: DetectionLanguageContext,
    ) -> TelegramDetectionResult:
        """Run URL-based detection pipeline."""
        logger.info("telegram_detect_url", user_id=user_id, url=url)

        result_dto, limits_dto = await self._url_detection.detect_from_url(
            url=url,
            user_id=user_id,
            language=language,
        )

        return self._build_result(
            result_dto=result_dto,
            limits_dto=limits_dto,
            source_label="url",
            detection_kind="url",
        )

    # ── private ───────────────────────────────────────────────────────────────

    @staticmethod
    def _build_result(
        result_dto: AIDetectionResultDTO,
        limits_dto: UserLimitDTO,
        source_label: str,
        detection_kind: DetectionKind,
    ) -> TelegramDetectionResult:
        meta = result_dto.metadata or {}
        req = meta.get("language_requested", "auto")
        eff = meta.get("language_effective", "ru")
        if isinstance(req, str):
            language_requested = req
        else:
            language_requested = getattr(req, "value", str(req))
        if isinstance(eff, str):
            language_effective = eff
        else:
            language_effective = str(eff)

        return TelegramDetectionResult(
            result=result_dto.result,
            confidence=result_dto.confidence,
            processing_time_ms=meta.get("processing_time_ms", 0),
            word_count=meta.get("word_count", len(result_dto.text_preview.split())),
            source_label=source_label,
            file_name=result_dto.file_name,
            daily_remaining=limits_dto.daily_remaining,
            monthly_remaining=limits_dto.monthly_remaining,
            language_requested=language_requested,
            language_effective=language_effective,
            detection_kind=detection_kind,
        )
