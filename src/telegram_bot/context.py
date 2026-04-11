"""Per-session Telegram handler dependencies (one DB unit of work)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.repositories.ai_detection_repository import AIDetectionRepository
    from src.repositories.auth_repository import AuthRepository
    from src.repositories.subscription_repository import SubscriptionRepository
    from src.services.ai_detection_service import AIDetectionService
    from src.services.rate_limiter_service import RateLimiterService
    from src.services.stripe_service import StripeService
    from src.services.telegram_detection_service import TelegramDetectionService


@dataclass
class TelegramSessionContext:
    """Services and repositories sharing one AsyncSession."""

    auth: AuthRepository
    ai_repo: AIDetectionRepository
    sub_repo: SubscriptionRepository
    ai_detection: AIDetectionService
    telegram_detection: TelegramDetectionService
    stripe: StripeService
    rate_limiter: RateLimiterService | None
