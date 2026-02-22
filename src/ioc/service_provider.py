"""
Service provider for dependency injection.
"""

from dishka import Provider, Scope, provide

from src.core.config import Config
from src.repositories.auth_repository import AuthRepository
from src.repositories.ai_detection_repository import AIDetectionRepository
from src.services.auth_service import AuthService
from src.services.gemini_service import GeminiTextExtractor
from src.services.newspaper_service import NewspaperService
from src.services.ml_model_service import AIDetectionModelService
from src.services.ai_detection_service import AIDetectionService
from src.services.telegram_detection_service import TelegramDetectionService
from src.services.url_detection_service import URLDetectionService


class ServiceProvider(Provider):
    """Provider for service dependencies."""

    @provide(scope=Scope.REQUEST)
    def get_auth_service(
        self, auth_repository: AuthRepository, config: Config
    ) -> AuthService:
        return AuthService(auth_repository, config)

    # ── Stateless singletons (APP scope) ──────────────────────────────────

    @provide(scope=Scope.APP)
    def get_gemini_service(self) -> GeminiTextExtractor:
        """Gemini AI service for file text extraction (PDF, DOCX, etc.)."""
        return GeminiTextExtractor()

    @provide(scope=Scope.APP)
    def get_ml_model_service(self) -> AIDetectionModelService:
        """ML microservice client for AI text detection inference."""
        return AIDetectionModelService()

    @provide(scope=Scope.APP)
    def get_newspaper_service(self) -> NewspaperService:
        """
        Newspaper service for downloading and extracting article text from URLs.

        Replaces the former JinaReaderService + TextCleanerService pair.
        newspaper4k handles fetching, HTML parsing, boilerplate removal,
        and returns clean plain text directly.
        """
        return NewspaperService()

    # ── Per-request services (REQUEST scope) ──────────────────────────────

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
            ai_detection_repository,
        )

    @provide(scope=Scope.REQUEST)
    def get_url_detection_service(
        self,
        newspaper_service: NewspaperService,
        ml_model_service: AIDetectionModelService,
        ai_detection_repository: AIDetectionRepository,
    ) -> URLDetectionService:
        """
        URL detection service wired with NewspaperService instead of Jina.

        TextCleanerService is no longer needed — newspaper returns plain text.
        """
        return URLDetectionService(
            newspaper_service,
            ml_model_service,
            ai_detection_repository,
        )

    @provide(scope=Scope.REQUEST)
    def get_telegram_detection_service(
        self,
        ai_detection_service: AIDetectionService,
    ) -> TelegramDetectionService:
        """
        Telegram-specific detection façade.

        Scoped to REQUEST so it shares the same AIDetectionService
        (and therefore the same DB session) as the rest of the request graph.
        """
        return TelegramDetectionService(ai_detection_service)