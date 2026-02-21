"""
ML Model service for AI text detection.

This service handles interaction with the ML microservice that detects
whether text is AI-generated or human-written.
"""

import httpx
from typing import Tuple

from src.core.logging import get_logger
from src.dtos.ai_detection_dto import DetectionResult

logger = get_logger(__name__)

ML_API_URL = "http://ml-api:8000"


class AIDetectionModelService:
    """Service for AI text detection via ML microservice."""

    def __init__(self):
        """Initialize AI detection model service."""
        self._client = httpx.AsyncClient(base_url=ML_API_URL, timeout=30.0)
        logger.info("ai_detection_model_initialized")

    async def detect_ai_text(self, text: str) -> Tuple[DetectionResult, float]:
        """
        Detect if text is AI-generated or human-written.

        Args:
            text: Text to analyze

        Returns:
            Tuple of (DetectionResult, confidence_score)
            confidence_score is between 0.0 and 1.0
        """
        try:
            logger.info("analyzing_text", text_length=len(text))

            response = await self._client.post(
                "/detect",
                json={"text": text},
            )
            response.raise_for_status()

            data = response.json()
            label: str = data["label"]
            ai_probability: float = data["ai_probability"]
            certainty: float = data["certainty"]

            result = self._map_label(label, ai_probability)
            confidence = round(certainty, 3)

            logger.info(
                "detection_complete",
                result=result.value,
                confidence=confidence,
                text_length=len(text),
                model_used=data.get("model_used"),
            )

            return result, confidence

        except httpx.HTTPStatusError as e:
            logger.error(
                "detection_request_failed",
                status_code=e.response.status_code,
                error=str(e),
                exc_info=True,
            )
            raise
        except httpx.RequestError as e:
            logger.error(
                "detection_connection_failed",
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True,
            )
            raise
        except Exception as e:
            logger.error(
                "detection_failed",
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True,
            )
            raise

    def _map_label(self, label: str, ai_probability: float) -> DetectionResult:
        """
        Map ML API label string to DetectionResult enum.

        Args:
            label: Label returned by the ML API (e.g. "ai", "human", "mixed")
            ai_probability: AI probability score as fallback

        Returns:
            DetectionResult enum value
        """
        normalized = label.lower()

        if normalized in ("ai", "ai_generated", "artificial"):
            return DetectionResult.AI_GENERATED
        if normalized in ("human", "human_written"):
            return DetectionResult.HUMAN_WRITTEN
        if normalized in ("mixed", "uncertain"):
            return DetectionResult.UNCERTAIN

        # Fallback: derive from probability if label is unrecognized
        logger.warning("unknown_label", label=label)
        if ai_probability > 0.7:
            return DetectionResult.AI_GENERATED
        if ai_probability < 0.4:
            return DetectionResult.HUMAN_WRITTEN
        return DetectionResult.UNCERTAIN

    def validate_text(self, text: str) -> bool:
        """
        Validate if text is suitable for detection.

        Args:
            text: Text to validate

        Returns:
            True if text is valid for detection
        """
        if not text or not text.strip():
            return False

        if len(text.strip()) < 50:
            logger.warning("text_too_short", text_length=len(text))
            return False

        return True

    async def close(self):
        """Close the underlying HTTP client."""
        await self._client.aclose()