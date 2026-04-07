"""
Subscription repository for database operations.
"""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.logging import get_logger
from src.models.subscription import Subscription

logger = get_logger(__name__)


class SubscriptionRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_user_id(self, user_id: str) -> Optional[Subscription]:
        result = await self.session.execute(
            select(Subscription).where(Subscription.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_by_stripe_subscription_id(
        self, stripe_subscription_id: str
    ) -> Optional[Subscription]:
        result = await self.session.execute(
            select(Subscription).where(
                Subscription.stripe_subscription_id == stripe_subscription_id
            )
        )
        return result.scalar_one_or_none()

    async def upsert(
        self,
        user_id: str,
        stripe_subscription_id: str,
        status: str,
        plan_type: str = "premium",
        current_period_end=None,
        cancel_at_period_end: bool = False,
    ) -> Subscription:
        """Create or update a subscription keyed by user_id."""
        sub = await self.get_by_user_id(user_id)
        if sub is None:
            sub = Subscription(
                user_id=user_id,
                stripe_subscription_id=stripe_subscription_id,
                status=status,
                plan_type=plan_type,
                current_period_end=current_period_end,
                cancel_at_period_end=cancel_at_period_end,
            )
            self.session.add(sub)
        else:
            sub.stripe_subscription_id = stripe_subscription_id
            sub.status = status
            sub.plan_type = plan_type
            sub.current_period_end = current_period_end
            sub.cancel_at_period_end = cancel_at_period_end

        await self.session.flush()
        await self.session.refresh(sub)

        logger.info(
            "subscription_upserted",
            user_id=user_id,
            stripe_subscription_id=stripe_subscription_id,
            status=status,
        )
        return sub
