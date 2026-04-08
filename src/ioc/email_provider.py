"""
Email service provider (APP-scoped).
"""

from dishka import Provider, Scope, provide

from src.core.config import Config
from src.services.email_service import EmailService, build_email_service


class EmailProvider(Provider):
    @provide(scope=Scope.APP)
    def get_email_service(self, config: Config) -> EmailService:
        return build_email_service(config)
