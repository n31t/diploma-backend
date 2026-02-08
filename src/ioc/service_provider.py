"""
Service provider for dependency injection.

This module provides all service dependencies.
"""

from dishka import Provider, Scope, provide

from src.core.config import Config
from src.repositories.auth_repository import AuthRepository
from src.services.auth_service import AuthService


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
