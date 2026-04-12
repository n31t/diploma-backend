"""
Service provider for dependency injection.
"""

from dishka import Provider, Scope, provide

from src.core.config import Config
from src.repositories.auth_repository import AuthRepository
from src.repositories.ai_detection_repository import AIDetectionRepository
from src.repositories.subscription_repository import SubscriptionRepository
from src.services.auth_service import AuthService
from src.services.google_oauth_client import GoogleOAuthClient
from src.services.email_service import EmailService
from src.services.gemini_service import GeminiTextExtractor
from src.services.newspaper_service import NewspaperService
from src.services.ml_model_service import AIDetectionModelService
from src.services.ai_detection_service import AIDetectionService
from src.services.stripe_service import StripeService
from src.services.telegram_detection_service import TelegramDetectionService
from src.services.text_normalization_service import TextNormalizationService
from src.services.url_detection_service import URLDetectionService


class ServiceProvider(Provider):
    """Provider for service dependencies."""

    @provide(scope=Scope.APP)
    def get_google_oauth_client(self, config: Config) -> GoogleOAuthClient:
        return GoogleOAuthClient(config)

    @provide(scope=Scope.REQUEST)
    def get_auth_service(
        self,
        auth_repository: AuthRepository,
        config: Config,
        email_service: EmailService,
        google_oauth_client: GoogleOAuthClient,
    ) -> AuthService:
        return AuthService(
            auth_repository, config, email_service, google_oauth_client
        )

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
        """URL article extraction: httpx download + newspaper4k + BeautifulSoup fallbacks."""
        return NewspaperService()

    @provide(scope=Scope.APP)
    def get_normalization_service(self) -> TextNormalizationService:
        """Style-preserving text normalization for the AI-detection pipeline."""
        return TextNormalizationService()

    # ── Per-request services (REQUEST scope) ──────────────────────────────

    @provide(scope=Scope.REQUEST)
    def get_ai_detection_service(
        self,
        gemini_service: GeminiTextExtractor,
        ml_model_service: AIDetectionModelService,
        ai_detection_repository: AIDetectionRepository,
        normalization_service: TextNormalizationService,
    ) -> AIDetectionService:
        return AIDetectionService(
            gemini_service,
            ml_model_service,
            ai_detection_repository,
            normalization_service,
        )

    @provide(scope=Scope.REQUEST)
    def get_url_detection_service(
        self,
        newspaper_service: NewspaperService,
        ml_model_service: AIDetectionModelService,
        ai_detection_repository: AIDetectionRepository,
        normalization_service: TextNormalizationService,
    ) -> URLDetectionService:
        return URLDetectionService(
            newspaper_service,
            ml_model_service,
            ai_detection_repository,
            normalization_service,
        )

    @provide(scope=Scope.REQUEST)
    def get_telegram_detection_service(
        self,
        ai_detection_service: AIDetectionService,
        url_detection_service: URLDetectionService,
    ) -> TelegramDetectionService:
        """
        Telegram-specific detection façade.

        Scoped to REQUEST so it shares the same AIDetectionService
        (and therefore the same DB session) as the rest of the request graph.
        """
        return TelegramDetectionService(ai_detection_service, url_detection_service)

    @provide(scope=Scope.REQUEST)
    def get_stripe_service(
        self,
        config: Config,
        subscription_repo: SubscriptionRepository,
        ai_detection_repo: AIDetectionRepository,
        auth_repo: AuthRepository,
    ) -> StripeService:
        return StripeService(config, subscription_repo, ai_detection_repo, auth_repo)