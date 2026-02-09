"""
Repository provider for dependency injection.
"""

from dishka import Provider, Scope, provide
from sqlalchemy.ext.asyncio import AsyncSession

from src.repositories.auth_repository import AuthRepository
from src.repositories.ai_detection_repository import AIDetectionRepository


class RepositoryProvider(Provider):
    """Provider for repository dependencies."""

    @provide(scope=Scope.REQUEST)
    def get_auth_repository(self, session: AsyncSession) -> AuthRepository:
        return AuthRepository(session)

    @provide(scope=Scope.REQUEST)
    def get_ai_detection_repository(self, session: AsyncSession) -> AIDetectionRepository:
        return AIDetectionRepository(session)