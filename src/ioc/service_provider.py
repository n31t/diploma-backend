"""
Service provider for dependency injection.

This module provides all service dependencies.
"""

from dishka import Provider, Scope, provide

from src.core.config import Config
from src.repositories.auth_repository import AuthRepository
from src.services.auth_service import AuthService
from src.services.gemini_service import GeminiTextExtractor
from src.services.ml_model_service import AIDetectionModelService
from src.services.ai_detection_service import AIDetectionService


class ServiceProvider(Provider):
    """
    Provider for service dependencies.

    All services are provided at REQUEST scope.
    """

    @provide(scope=Scope.REQUEST)
    def get_auth_service(
        self, auth_repository: AuthRepository, config: Config
    ) -> AuthService:
        """
        Provide AuthService for the current request.

        Args:
            auth_repository: Authentication repository
            config: Application configuration

        Returns:
            AuthService instance
        """
        return AuthService(auth_repository, config)

    @provide(scope=Scope.APP)
    def get_gemini_service(self) -> GeminiTextExtractor:
        """
        Provide GeminiTextExtractor as singleton.

        Returns:
            GeminiTextExtractor instance
        """
        return GeminiTextExtractor()

    @provide(scope=Scope.APP)
    def get_ml_model_service(self) -> AIDetectionModelService:
        """
        Provide AIDetectionModelService as singleton.

        Returns:
            AIDetectionModelService instance
        """
        return AIDetectionModelService()

    @provide(scope=Scope.REQUEST)
    def get_ai_detection_service(
        self,
        gemini_service: GeminiTextExtractor,
        ml_model_service: AIDetectionModelService,
    ) -> AIDetectionService:
        """
        Provide AIDetectionService for the current request.

        Args:
            gemini_service: Gemini text extraction service
            ml_model_service: ML model detection service

        Returns:
            AIDetectionService instance
        """
        return AIDetectionService(gemini_service, ml_model_service)