"""
Service provider for dependency injection.
"""

from dishka import Provider, Scope, provide

from src.core.config import Config
from src.repositories.auth_repository import AuthRepository
from src.repositories.ai_detection_repository import AIDetectionRepository
from src.services.auth_service import AuthService
from src.services.gemini_service import GeminiTextExtractor
from src.services.ml_model_service import AIDetectionModelService
from src.services.ai_detection_service import AIDetectionService


class ServiceProvider(Provider):
    """Provider for service dependencies."""

    @provide(scope=Scope.REQUEST)
    def get_auth_service(
        self, auth_repository: AuthRepository, config: Config
    ) -> AuthService:
        return AuthService(auth_repository, config)

    @provide(scope=Scope.APP)
    def get_gemini_service(self) -> GeminiTextExtractor:
        return GeminiTextExtractor()

    @provide(scope=Scope.APP)
    def get_ml_model_service(self) -> AIDetectionModelService:
        return AIDetectionModelService()

    @provide(scope=Scope.REQUEST)
    def get_ai_detection_service(
        self,
        gemini_service: GeminiTextExtractor,
        ml_model_service: AIDetectionModelService,
        ai_detection_repository: AIDetectionRepository,
    ) -> AIDetectionService:
        return AIDetectionService(
            gemini_service,
            ml_model_service,
            ai_detection_repository
        )