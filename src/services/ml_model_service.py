"""
ML Model service for AI text detection.

This service handles interaction with the ML microservice that detects
whether text is AI-generated or human-written.
"""

import os
import httpx
from typing import Tuple, Any, Iterable

from src.core.logging import get_logger
from src.dtos.ai_detection_dto import DetectionResult

logger = get_logger(__name__)

# Allow overriding the ML API base URL via environment variable for tests and deployments
ML_API_URL = os.getenv("ML_API_URL", "http://ml-api:8000")


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
                "/api/v1/detection/",
                json={"text": text},
            )
            response.raise_for_status()

            # Attempt to parse robustly — accept a few shapes and fallback safely
            try:
                data = response.json()
                if "data" in data:
                    data = data["data"]
            except Exception:
                # If response is not JSON, log and fallback
                text_content = (await response.aread()).decode("utf-8", errors="replace")
                logger.error("detection_invalid_json", response_text=text_content)
                return DetectionResult.UNCERTAIN, 0.0

            # Normalize to dict when possible
            if not isinstance(data, dict):
                # e.g. some services return a list or other container — log and try to coerce
                logger.warning("detection_unexpected_payload_type", payload_type=type(data).__name__, payload_preview=str(data)[:500])

            # Helper to pull candidate keys (supports nested dot paths)
            def _extract(data_obj: Any, candidates: Iterable[str]) -> Any:
                for cand in candidates:
                    if isinstance(data_obj, dict) and cand in data_obj:
                        return data_obj[cand]
                    # nested lookup using dot notation
                    if "." in cand:
                        cur = data_obj
                        parts = cand.split(".")
                        ok = True
                        for p in parts:
                            if isinstance(cur, dict) and p in cur:
                                cur = cur[p]
                            else:
                                ok = False
                                break
                        if ok:
                            return cur
                    # if data is list and candidate is numeric index
                    if isinstance(data_obj, list):
                        try:
                            idx = int(cand)
                            if 0 <= idx < len(data_obj):
                                return data_obj[idx]
                        except Exception:
                            pass
                return None

            # Try a number of likely key names used by different ML services
            label = _extract(data, ["label", "result", "prediction", "predicted_label", "output.label"])
            ai_probability = _extract(data, ["ai_probability", "probability", "ai_prob", "score", "prob", "predicted_probability"])
            certainty = _extract(data, ["certainty", "confidence", "score", "certainty_score"])

            # If keys missing, log response for debugging and try to derive from available fields
            if label is None:
                logger.warning("unknown_label_in_response", response_preview=str(data)[:1000])

            # Normalize numeric fields
            def _to_float(val: Any) -> float | None:
                if val is None:
                    return None
                try:
                    return float(val)
                except Exception:
                    return None

            ai_probability_f = _to_float(ai_probability)
            certainty_f = _to_float(certainty)

            # Determine result by label first, then by probability fallback
            if isinstance(label, str):
                result = self._map_label(label, ai_probability_f or 0.0)
            else:
                # Fallback using probability alone
                if ai_probability_f is not None:
                    if ai_probability_f > 0.7:
                        result = DetectionResult.AI_GENERATED
                    elif ai_probability_f < 0.4:
                        result = DetectionResult.HUMAN_WRITTEN
                    else:
                        result = DetectionResult.UNCERTAIN
                else:
                    result = DetectionResult.UNCERTAIN

            # Confidence: prefer explicit certainty, then ai_probability, else 0.0
            confidence = round(float(certainty_f if certainty_f is not None else (ai_probability_f if ai_probability_f is not None else 0.0)), 3)

            logger.info(
                "detection_complete",
                result=result.value,
                confidence=confidence,
                text_length=len(text),
                model_used=_extract(data, ["model", "model_used", "modelName"]),
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
            # Catch parsing/key errors and return a safe fallback instead of raising KeyError
            logger.error(
                "detection_failed",
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True,
            )
            return DetectionResult.UNCERTAIN, 0.0

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