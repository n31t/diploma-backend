"""
Gemini service for text extraction from files.

This service handles interaction with Google's Gemini AI model
to extract text from various file formats.
"""

import asyncio
import logging
import os
import tempfile
from typing import Optional

import google.generativeai as genai
from google.generativeai.types import HarmBlockThreshold, HarmCategory

from src.core.gemini_config import gemini_config
from src.core.logging import get_logger

logger = get_logger(__name__)


class GeminiTextExtractor:
    """Service for extracting text from files using Gemini."""

    def __init__(self):
        """Initialize Gemini text extractor."""
        genai.configure(api_key=gemini_config.GEMINI_API_KEY)
        self.model = genai.GenerativeModel(gemini_config.GEMINI_MODEL)
        self.safety_settings = {
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
        }

    async def extract_text_from_file(self, file_path: str, file_name: str) -> str:
        """
        Extract text from a file using Gemini.

        Args:
            file_path: Path to the temporary file
            file_name: Original name of the file

        Returns:
            Extracted text content

        Raises:
            Exception: If text extraction fails
        """
        uploaded_file = None
        try:
            logger.info(
                "uploading_file_to_gemini",
                file_name=file_name
            )

            # Upload file to Gemini
            uploaded_file = genai.upload_file(file_path)

            # Wait for file processing
            logger.info("waiting_for_file_processing", file_name=file_name)
            await self._wait_for_file_processing(uploaded_file.name)

            # Extract text using Gemini
            extraction_prompt = """
            Extract all text content from this document. 
            Return only the extracted text without any additional commentary or formatting.
            Preserve the original structure and organization of the text as much as possible.
            If the document contains tables, preserve them in a readable format.
            """

            response = self.model.generate_content(
                contents=[extraction_prompt, uploaded_file],
                safety_settings=self.safety_settings,
            )

            text = self.extract_text_safe(response)
            if not text or not text.strip():
                raise ValueError("No readable text found in document")

            logger.info(
                "text_extraction_successful",
                file_name=file_name,
                text_length=len(response.text)
            )

            return response.text.strip()

        except Exception as e:
            logger.error(
                "text_extraction_failed",
                file_name=file_name,
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True
            )
            raise RuntimeError(f"Failed to extract text from file: {str(e)}")

        finally:
            # Clean up uploaded file from Gemini
            if uploaded_file:
                try:
                    genai.delete_file(uploaded_file.name)
                    logger.debug("gemini_file_deleted", file_name=file_name)
                except Exception as e:
                    logger.warning(
                        "failed_to_delete_gemini_file",
                        file_name=file_name,
                        error=str(e)
                    )

    async def _wait_for_file_processing(self, file_name: str, max_retries: int = 10, retry_delay: int = 5):
        """
        Wait for uploaded file to be processed by Gemini.

        Args:
            file_name: Name of the uploaded file in Gemini
            max_retries: Maximum number of retries
            retry_delay: Delay between retries in seconds

        Raises:
            Exception: If file processing times out
        """
        for attempt in range(max_retries):
            try:
                file_info = genai.get_file(file_name)
                # State 2 = PROCESSED, State 1 = PENDING
                if file_info.state == 2:
                    logger.debug(
                        "file_processing_complete",
                        file_name=file_name,
                        attempt=attempt + 1
                    )
                    return

                logger.info(
                    "file_processing_pending",
                    file_name=file_name,
                    state=file_info.state,
                    attempt=attempt + 1,
                    retry_in=retry_delay
                )
                await asyncio.sleep(retry_delay)

            except Exception as e:
                logger.warning(
                    "error_checking_file_status",
                    file_name=file_name,
                    attempt=attempt + 1,
                    error=str(e)
                )
                await asyncio.sleep(retry_delay)

        raise Exception(f"File processing timed out after {max_retries * retry_delay} seconds")

    @staticmethod
    def extract_text_safe(response) -> str | None:
        if not response.candidates:
            return None

        parts = response.candidates[0].content.parts
        texts = [
            part.text
            for part in parts
            if hasattr(part, "text") and part.text.strip()
        ]

        return "\n".join(texts) if texts else None