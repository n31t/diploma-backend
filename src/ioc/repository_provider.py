"""
Repository provider for dependency injection.

This module provides all repository dependencies.
"""

from dishka import Provider, Scope, provide
from sqlalchemy.ext.asyncio import AsyncSession

from src.repositories.auth_repository import AuthRepository


class RepositoryProvider(Provider):
    """
    Provider for repository dependencies.

    All repositories are provided at REQUEST scope.
    """

    @provide(scope=Scope.REQUEST)
    def get_auth_repository(self, session: AsyncSession) -> AuthRepository:
        """
        Provide AuthRepository for the current request.

        Args:
            session: Database session

        Returns:
            AuthRepository instance
        """
        return AuthRepository(session)
