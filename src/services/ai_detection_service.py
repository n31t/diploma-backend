"""
AI Detection service layer with limits and history tracking.
"""

import os
import tempfile
import time
from typing import Optional

from src.core.gemini_config import gemini_config
from src.core.logging import get_logger
from src.dtos.ai_detection_dto import (
    AIDetectionResultDTO,
    DetectionSource,
)
from src.dtos.limits_dto import UserLimitDTO
from src.repositories.ai_detection_repository import AIDetectionRepository
from src.services.gemini_service import GeminiTextExtractor
from src.services.ml_model_service import AIDetectionModelService

logger = get_logger(__name__)


class AIDetectionService:
    """Service for AI text detection with limits and history."""

    def __init__(
        self,
        gemini_service: GeminiTextExtractor,
        ml_model_service: AIDetectionModelService,
        ai_detection_repository: AIDetectionRepository,
    ):
        self.gemini_service = gemini_service
        self.ml_model_service = ml_model_service
        self.ai_detection_repository = ai_detection_repository

    async def check_user_limits(self, user_id: str) -> UserLimitDTO:
        """
        Check user limits and return limit information.

        Args:
            user_id: User ID

        Returns:
            UserLimitDTO with limit information

        Raises:
            ValueError: If user has exceeded limits
        """
        can_request, user_limit = await self.ai_detection_repository.can_make_request(user_id)

        limit_dto = UserLimitDTO.from_model(user_limit)

        if not can_request:
            logger.warning(
                "user_limit_exceeded",
                user_id=user_id,
                daily_used=user_limit.daily_used,
                daily_limit=user_limit.daily_limit,
                monthly_used=user_limit.monthly_used,
                monthly_limit=user_limit.monthly_limit
            )
            raise ValueError(
                f"Request limit exceeded. "
                f"Daily: {user_limit.daily_used}/{user_limit.daily_limit}, "
                f"Monthly: {user_limit.monthly_used}/{user_limit.monthly_limit}"
            )

        return limit_dto

    async def detect_from_text(
        self,
        text: str,
        user_id: str
    ) -> tuple[AIDetectionResultDTO, UserLimitDTO]:
        """
        Detect AI-generated text from provided text string.

        Args:
            text: Text to analyze
            user_id: User ID

        Returns:
            Tuple of (AIDetectionResultDTO, UserLimitDTO)

        Raises:
            ValueError: If text is invalid or limits exceeded
        """
        start_time = time.time()

        logger.info("detecting_from_text", text_length=len(text), user_id=user_id)

        # Check limits
        await self.check_user_limits(user_id)

        # Validate text
        if not self.ml_model_service.validate_text(text):
            raise ValueError("Text is too short or invalid. Minimum 50 characters required.")

        try:
            # Run AI detection
            result, confidence = await self.ml_model_service.detect_ai_text(text)

            # Calculate processing time
            processing_time_ms = int((time.time() - start_time) * 1000)

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
                    "processing_time_ms": processing_time_ms,
                }
            )

            # Increment usage
            user_limit = await self.ai_detection_repository.increment_usage(user_id)

            # Save to history
            await self.ai_detection_repository.create_history_record(
                user_id=user_id,
                source="text",
                result=result.value,
                confidence=confidence,
                text_preview=text[:500],
                text_length=len(text),
                word_count=len(text.split()),
                processing_time_ms=processing_time_ms
            )

            logger.info(
                "detection_from_text_complete",
                user_id=user_id,
                result=result.value,
                confidence=confidence,
                processing_time_ms=processing_time_ms
            )

            return detection_result, UserLimitDTO.from_model(user_limit)

        except Exception as e:
            logger.error(
                "detection_from_text_failed",
                user_id=user_id,
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
        user_id: str
    ) -> tuple[AIDetectionResultDTO, UserLimitDTO]:
        """
        Detect AI-generated text from uploaded file.

        Args:
            file_content: File content as bytes
            file_name: Original file name
            content_type: MIME type of the file
            user_id: User ID

        Returns:
            Tuple of (AIDetectionResultDTO, UserLimitDTO)

        Raises:
            ValueError: If file is invalid or limits exceeded
        """
        start_time = time.time()

        logger.info(
            "detecting_from_file",
            file_name=file_name,
            content_type=content_type,
            file_size=len(file_content),
            user_id=user_id
        )

        # Check limits
        await self.check_user_limits(user_id)

        # Validate file
        self._validate_file(file_name, file_content)

        temp_path = None
        try:
            # Save file to temporary location
            temp_path = await self._save_temp_file(file_content, file_name)

            # Extract text using Gemini
            logger.info("extracting_text_from_file", file_name=file_name, user_id=user_id)
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

            # Calculate processing time
            processing_time_ms = int((time.time() - start_time) * 1000)

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
                    "processing_time_ms": processing_time_ms,
                }
            )

            # Increment usage
            user_limit = await self.ai_detection_repository.increment_usage(user_id)

            # Save to history
            await self.ai_detection_repository.create_history_record(
                user_id=user_id,
                source="file",
                result=result.value,
                confidence=confidence,
                text_preview=extracted_text[:500],
                text_length=len(extracted_text),
                word_count=len(extracted_text.split()),
                file_name=file_name,
                file_size=len(file_content),
                content_type=content_type,
                processing_time_ms=processing_time_ms
            )

            logger.info(
                "detection_from_file_complete",
                file_name=file_name,
                user_id=user_id,
                result=result.value,
                confidence=confidence,
                processing_time_ms=processing_time_ms
            )

            return detection_result, UserLimitDTO.from_model(user_limit)

        except ValueError as e:
            logger.error(
                "detection_from_file_validation_failed",
                file_name=file_name,
                user_id=user_id,
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True
            )
            raise
        except Exception as e:
            logger.error(
                "detection_from_file_failed",
                file_name=file_name,
                user_id=user_id,
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

    async def get_user_limits(self, user_id: str) -> UserLimitDTO:
        """
        Get user limit information.

        Args:
            user_id: User ID

        Returns:
            UserLimitDTO with current limits
        """
        user_limit = await self.ai_detection_repository.get_or_create_user_limit(user_id)
        user_limit = await self.ai_detection_repository.check_and_reset_limits(user_limit)
        return UserLimitDTO.from_model(user_limit)

    def _validate_file(self, file_name: str, file_content: bytes):
        """Validate uploaded file."""
        file_size_mb = len(file_content) / (1024 * 1024)
        if file_size_mb > gemini_config.MAX_FILE_SIZE_MB:
            raise ValueError(
                f"File size ({file_size_mb:.2f}MB) exceeds maximum "
                f"allowed size ({gemini_config.MAX_FILE_SIZE_MB}MB)"
            )

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
        """Save file content to temporary file."""
        _, ext = os.path.splitext(file_name)
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
        temp_file.write(file_content)
        temp_file.close()

        logger.debug(
            "temp_file_created",
            file_name=file_name,
            temp_path=temp_file.name
        )

        return temp_file.name