"""
AI Detection service layer for business logic.

This service orchestrates text extraction via Gemini and AI detection
via ML model, handling the complete workflow.
"""

import os
import tempfile
from typing import Optional

from src.core.gemini_config import gemini_config
from src.core.logging import get_logger
from src.dtos.ai_detection_dto import (
    AIDetectionRequestDTO,
    AIDetectionResultDTO,
    DetectionSource,
    TextExtractionDTO,
)
from src.services.gemini_service import GeminiTextExtractor
from src.services.ml_model_service import AIDetectionModelService

logger = get_logger(__name__)


class AIDetectionService:
    """Service for AI text detection workflow."""

    def __init__(
        self,
        gemini_service: GeminiTextExtractor,
        ml_model_service: AIDetectionModelService,
    ):
        """
        Initialize AI detection service.

        Args:
            gemini_service: Service for text extraction from files
            ml_model_service: Service for AI text detection
        """
        self.gemini_service = gemini_service
        self.ml_model_service = ml_model_service

    async def detect_from_text(self, text: str) -> AIDetectionResultDTO:
        """
        Detect AI-generated text from provided text string.

        Args:
            text: Text to analyze

        Returns:
            AIDetectionResultDTO with detection results

        Raises:
            ValueError: If text is invalid
        """
        logger.info("detecting_from_text", text_length=len(text))

        # Validate text
        if not self.ml_model_service.validate_text(text):
            raise ValueError("Text is too short or invalid. Minimum 50 characters required.")

        try:
            # Run AI detection
            result, confidence = await self.ml_model_service.detect_ai_text(text)

            # Create result DTO
            detection_result = AIDetectionResultDTO(
                result=result,
                confidence=confidence,
                text_preview=text[:200],
                source=DetectionSource.TEXT,
                file_name=None,
                metadata={
                    "text_length": len(text),
                    "word_count": len(text.split()),
                }
            )

            logger.info(
                "detection_from_text_complete",
                result=result.value,
                confidence=confidence
            )

            return detection_result

        except Exception as e:
            logger.error(
                "detection_from_text_failed",
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True
            )
            raise

    async def detect_from_file(
        self,
        file_content: bytes,
        file_name: str,
        content_type: str,
    ) -> AIDetectionResultDTO:
        """
        Detect AI-generated text from uploaded file.

        Args:
            file_content: File content as bytes
            file_name: Original file name
            content_type: MIME type of the file

        Returns:
            AIDetectionResultDTO with detection results

        Raises:
            ValueError: If file is invalid
            Exception: If processing fails
        """
        logger.info(
            "detecting_from_file",
            file_name=file_name,
            content_type=content_type,
            file_size=len(file_content)
        )

        # Validate file
        self._validate_file(file_name, file_content)

        temp_path = None
        try:
            # Save file to temporary location
            temp_path = await self._save_temp_file(file_content, file_name)

            # Extract text using Gemini
            logger.info("extracting_text_from_file", file_name=file_name)
            extracted_text = await self.gemini_service.extract_text_from_file(
                temp_path, file_name
            )

            # Validate extracted text
            if not self.ml_model_service.validate_text(extracted_text):
                raise ValueError(
                    "Extracted text is too short or invalid. "
                    "The file may not contain enough text content."
                )

            # Run AI detection on extracted text
            result, confidence = await self.ml_model_service.detect_ai_text(extracted_text)

            # Create result DTO
            detection_result = AIDetectionResultDTO(
                result=result,
                confidence=confidence,
                text_preview=extracted_text[:200],
                source=DetectionSource.FILE,
                file_name=file_name,
                metadata={
                    "file_size": len(file_content),
                    "content_type": content_type,
                    "extracted_text_length": len(extracted_text),
                    "word_count": len(extracted_text.split()),
                }
            )

            logger.info(
                "detection_from_file_complete",
                file_name=file_name,
                result=result.value,
                confidence=confidence
            )

            return detection_result

        except Exception as e:
            logger.error(
                "detection_from_file_failed",
                file_name=file_name,
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True
            )
            raise

        finally:
            # Clean up temporary file
            if temp_path and os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                    logger.debug("temp_file_deleted", file_name=file_name)
                except Exception as e:
                    logger.warning(
                        "failed_to_delete_temp_file",
                        file_name=file_name,
                        error=str(e)
                    )

    def _validate_file(self, file_name: str, file_content: bytes):
        """
        Validate uploaded file.

        Args:
            file_name: Original file name
            file_content: File content as bytes

        Raises:
            ValueError: If file is invalid
        """
        # Check file size
        file_size_mb = len(file_content) / (1024 * 1024)
        if file_size_mb > gemini_config.MAX_FILE_SIZE_MB:
            raise ValueError(
                f"File size ({file_size_mb:.2f}MB) exceeds maximum "
                f"allowed size ({gemini_config.MAX_FILE_SIZE_MB}MB)"
            )

        # Check file extension
        file_ext = os.path.splitext(file_name)[1].lower()
        if file_ext not in gemini_config.ALLOWED_FILE_EXTENSIONS:
            raise ValueError(
                f"File type '{file_ext}' not allowed. "
                f"Allowed types: {', '.join(gemini_config.ALLOWED_FILE_EXTENSIONS)}"
            )

        logger.debug(
            "file_validation_passed",
            file_name=file_name,
            file_size_mb=round(file_size_mb, 2),
            file_extension=file_ext
        )

    async def _save_temp_file(self, file_content: bytes, file_name: str) -> str:
        """
        Save file content to temporary file.

        Args:
            file_content: File content as bytes
            file_name: Original file name

        Returns:
            Path to temporary file
        """
        # Get file extension
        _, ext = os.path.splitext(file_name)

        # Create temporary file
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
        temp_file.write(file_content)
        temp_file.close()

        logger.debug(
            "temp_file_created",
            file_name=file_name,
            temp_path=temp_file.name
        )

        return temp_file.name