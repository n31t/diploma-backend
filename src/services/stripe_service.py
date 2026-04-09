"""
Stripe billing service.

Handles checkout sessions, customer portal, and webhook event processing.
Webhook is the sole writer of subscription state.
"""

from __future__ import annotations

from datetime import datetime, timezone

import stripe

from src.core.billing import (
    ACTIVE_SUBSCRIPTION_STATUSES,
    FREE_DAILY_LIMIT,
    FREE_MONTHLY_LIMIT,
    PREMIUM_DAILY_LIMIT,
    PREMIUM_MONTHLY_LIMIT,
)
from src.core.billing_exceptions import BillingServiceError
from src.core.config import Config
from src.core.logging import get_logger
from src.repositories.ai_detection_repository import AIDetectionRepository
from src.repositories.auth_repository import AuthRepository
from src.repositories.subscription_repository import SubscriptionRepository

logger = get_logger(__name__)


def _stripe_get(obj: object, key: str, default=None):
    """Read a field from a Stripe SDK object or a plain dict.

    StripeObject supports ``obj[key]`` and ``key in obj`` but not ``.get()``;
    ``obj.get("k")`` is interpreted as a missing API field and raises.
    """
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    try:
        if key not in obj:  # type: ignore[operator]
            return default
        return obj[key]  # type: ignore[index]
    except (KeyError, TypeError):
        return default


class StripeService:
    def __init__(
        self,
        config: Config,
        subscription_repo: SubscriptionRepository,
        ai_detection_repo: AIDetectionRepository,
        auth_repo: AuthRepository,
    ):
        self.config = config
        self.subscription_repo = subscription_repo
        self.ai_detection_repo = ai_detection_repo
        self.auth_repo = auth_repo

        if config.STRIPE_SECRET_KEY:
            stripe.api_key = config.STRIPE_SECRET_KEY

    # ------------------------------------------------------------------
    # Public: checkout / portal
    # ------------------------------------------------------------------

    async def create_checkout_session(self, user_id: str, email: str) -> str:
        """Return a Stripe Checkout URL for a new subscription."""
        customer_id = await self._get_or_create_customer(user_id, email)

        session = stripe.checkout.Session.create(
            customer=customer_id,
            mode="subscription",
            line_items=[{"price": self.config.STRIPE_PRICE_ID, "quantity": 1}],
            success_url=f"{self.config.FRONTEND_URL}/dashboard/billing/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{self.config.FRONTEND_URL}/dashboard/billing/cancel",
            client_reference_id=user_id,
            metadata={"user_id": user_id},
        )
        return session.url

    async def create_portal_session(self, user_id: str) -> str:
        """Return a Stripe Customer Portal URL for self-serve management."""
        user = await self.auth_repo.get_user_by_id(user_id)
        if not user or not user.stripe_customer_id:
            raise ValueError("No Stripe customer found for this user")

        session = stripe.billing_portal.Session.create(
            customer=user.stripe_customer_id,
            return_url=f"{self.config.FRONTEND_URL}/dashboard/billing",
        )
        return session.url

    # ------------------------------------------------------------------
    # Public: cancel / resume (Stripe API only; webhooks update local DB)
    # ------------------------------------------------------------------

    async def cancel_subscription_for_user(self, user_id: str) -> bool:
        """Request cancel at period end in Stripe. Returns True if already scheduled (idempotent).

        Does not write subscription rows or user_limits; webhooks sync state.
        """
        if not self.config.STRIPE_SECRET_KEY:
            logger.warning("stripe_cancel_skipped_no_secret_key", user_id=user_id)
            raise BillingServiceError(
                "STRIPE_NOT_CONFIGURED",
                "Stripe is not configured on this server",
                http_status=503,
            )

        sub = await self.subscription_repo.get_by_user_id(user_id)
        if sub is None:
            raise BillingServiceError(
                "NO_ACTIVE_SUBSCRIPTION",
                "No subscription found for this user",
                http_status=404,
            )

        if sub.status not in ACTIVE_SUBSCRIPTION_STATUSES:
            raise BillingServiceError(
                "NO_ACTIVE_SUBSCRIPTION",
                "No active subscription to cancel",
                http_status=404,
            )

        if sub.cancel_at_period_end:
            logger.info("cancellation_already_scheduled", user_id=user_id)
            return True

        try:
            stripe.Subscription.modify(sub.stripe_subscription_id, cancel_at_period_end=True)
        except stripe.error.StripeError as exc:
            logger.warning(
                "stripe_cancellation_failed",
                user_id=user_id,
                error=str(exc),
                error_type=type(exc).__name__,
            )
            raise BillingServiceError(
                "STRIPE_REQUEST_FAILED",
                "Could not schedule subscription cancellation",
                http_status=502,
            ) from exc

        logger.info("cancellation_requested", user_id=user_id, subscription_id=sub.stripe_subscription_id)
        return False

    async def resume_subscription_for_user(self, user_id: str) -> None:
        """Clear cancel-at-period-end in Stripe. Webhooks update local DB."""
        if not self.config.STRIPE_SECRET_KEY:
            logger.warning("stripe_resume_skipped_no_secret_key", user_id=user_id)
            raise BillingServiceError(
                "STRIPE_NOT_CONFIGURED",
                "Stripe is not configured on this server",
                http_status=503,
            )

        sub = await self.subscription_repo.get_by_user_id(user_id)
        if sub is None:
            raise BillingServiceError(
                "SUBSCRIPTION_NOT_FOUND",
                "No subscription found for this user",
                http_status=404,
            )

        if sub.status not in ACTIVE_SUBSCRIPTION_STATUSES:
            raise BillingServiceError(
                "NO_ACTIVE_SUBSCRIPTION",
                "Subscription is not active",
                http_status=404,
            )

        if not sub.cancel_at_period_end:
            raise BillingServiceError(
                "CANCELLATION_NOT_SCHEDULED",
                "Subscription is not scheduled for cancellation",
                http_status=409,
            )

        try:
            stripe.Subscription.modify(sub.stripe_subscription_id, cancel_at_period_end=False)
        except stripe.error.StripeError as exc:
            logger.warning(
                "stripe_resume_failed",
                user_id=user_id,
                error=str(exc),
                error_type=type(exc).__name__,
            )
            raise BillingServiceError(
                "STRIPE_REQUEST_FAILED",
                "Could not resume subscription",
                http_status=502,
            ) from exc

        logger.info("resume_requested", user_id=user_id, subscription_id=sub.stripe_subscription_id)

    # ------------------------------------------------------------------
    # Public: webhook
    # ------------------------------------------------------------------

    def verify_webhook(self, payload: bytes, sig_header: str) -> stripe.Event:
        """Verify Stripe webhook signature and return the parsed event."""
        return stripe.Webhook.construct_event(
            payload, sig_header, self.config.STRIPE_WEBHOOK_SECRET
        )

    async def handle_event(self, event: stripe.Event) -> None:
        """Dispatch a verified Stripe event to the appropriate handler."""
        handler = {
            "checkout.session.completed": self._handle_checkout_completed,
            "customer.subscription.created": self._handle_subscription_upsert,
            "customer.subscription.updated": self._handle_subscription_upsert,
            "customer.subscription.deleted": self._handle_subscription_deleted,
            "invoice.paid": self._handle_invoice_paid,
            "invoice.payment_failed": self._handle_invoice_payment_failed,
        }.get(event.type)

        if handler is None:
            logger.debug("stripe_event_ignored", event_type=event.type)
            return

        logger.info("stripe_event_processing", event_type=event.type, event_id=event.id)
        await handler(event)

    # ------------------------------------------------------------------
    # Private: event handlers
    # ------------------------------------------------------------------

    async def _handle_checkout_completed(self, event: stripe.Event) -> None:
        session = event.data.object
        user_id = _stripe_get(session, "client_reference_id")
        if not user_id:
            logger.warning(
                "checkout_missing_client_reference_id",
                session_id=_stripe_get(session, "id"),
            )
            return

        customer_id = _stripe_get(session, "customer")
        subscription_id = _stripe_get(session, "subscription")
        if not subscription_id:
            logger.warning(
                "checkout_missing_subscription",
                session_id=_stripe_get(session, "id"),
            )
            return

        # Persist stripe_customer_id on user
        await self._save_customer_id(user_id, customer_id)

        # Fetch full subscription object for period info
        sub_obj = stripe.Subscription.retrieve(subscription_id)
        period_end = _ts_to_dt(_stripe_get(sub_obj, "current_period_end"))

        await self.subscription_repo.upsert(
            user_id=user_id,
            stripe_subscription_id=subscription_id,
            status=_stripe_get(sub_obj, "status", "active"),
            current_period_end=period_end,
            cancel_at_period_end=_stripe_get(sub_obj, "cancel_at_period_end", False),
        )

        await self._apply_premium(user_id)
        logger.info("checkout_completed", user_id=user_id, subscription_id=subscription_id)

    async def _handle_subscription_upsert(self, event: stripe.Event) -> None:
        sub_obj = event.data.object
        subscription_id = _stripe_get(sub_obj, "id")
        customer_id = _stripe_get(sub_obj, "customer")
        status = _stripe_get(sub_obj, "status")

        user_id = await self._resolve_user_id(
            customer_id=customer_id,
            metadata=_stripe_get(sub_obj, "metadata"),
        )
        if not user_id:
            logger.warning("subscription_event_user_not_found", subscription_id=subscription_id)
            return

        await self.subscription_repo.upsert(
            user_id=user_id,
            stripe_subscription_id=subscription_id,
            status=status,
            current_period_end=_ts_to_dt(_stripe_get(sub_obj, "current_period_end")),
            cancel_at_period_end=_stripe_get(sub_obj, "cancel_at_period_end", False),
        )

        if status in ACTIVE_SUBSCRIPTION_STATUSES:
            await self._apply_premium(user_id)
        else:
            await self._apply_free(user_id)

        logger.info("subscription_upserted", user_id=user_id, status=status)

    async def _handle_subscription_deleted(self, event: stripe.Event) -> None:
        sub_obj = event.data.object
        subscription_id = _stripe_get(sub_obj, "id")
        customer_id = _stripe_get(sub_obj, "customer")

        user_id = await self._resolve_user_id(
            customer_id=customer_id,
            metadata=_stripe_get(sub_obj, "metadata"),
        )
        if not user_id:
            logger.warning("subscription_deleted_user_not_found", subscription_id=subscription_id)
            return

        await self.subscription_repo.upsert(
            user_id=user_id,
            stripe_subscription_id=subscription_id,
            status="canceled",
            current_period_end=_ts_to_dt(_stripe_get(sub_obj, "current_period_end")),
            cancel_at_period_end=True,
        )
        await self._apply_free(user_id)
        logger.info("subscription_canceled", user_id=user_id, subscription_id=subscription_id)

    async def _handle_invoice_paid(self, event: stripe.Event) -> None:
        invoice = event.data.object
        subscription_id = _stripe_get(invoice, "subscription")
        if not subscription_id:
            return

        sub = await self.subscription_repo.get_by_stripe_subscription_id(subscription_id)
        if not sub:
            logger.debug("invoice_paid_no_local_sub", subscription_id=subscription_id)
            return

        sub_obj = stripe.Subscription.retrieve(subscription_id)
        await self.subscription_repo.upsert(
            user_id=sub.user_id,
            stripe_subscription_id=subscription_id,
            status=_stripe_get(sub_obj, "status", "active"),
            current_period_end=_ts_to_dt(_stripe_get(sub_obj, "current_period_end")),
            cancel_at_period_end=_stripe_get(sub_obj, "cancel_at_period_end", False),
        )
        await self._apply_premium(sub.user_id)
        logger.info("invoice_paid", user_id=sub.user_id)

    async def _handle_invoice_payment_failed(self, event: stripe.Event) -> None:
        invoice = event.data.object
        subscription_id = _stripe_get(invoice, "subscription")
        customer_email = _stripe_get(invoice, "customer_email")
        logger.warning(
            "invoice_payment_failed",
            subscription_id=subscription_id,
            customer_email=customer_email,
        )

    # ------------------------------------------------------------------
    # Private: helpers
    # ------------------------------------------------------------------

    async def _get_or_create_customer(self, user_id: str, email: str) -> str:
        user = await self.auth_repo.get_user_by_id(user_id)
        if user and user.stripe_customer_id:
            return user.stripe_customer_id

        customer = stripe.Customer.create(email=email, metadata={"user_id": user_id})
        await self._save_customer_id(user_id, customer.id)
        return customer.id

    async def _save_customer_id(self, user_id: str, customer_id: str) -> None:
        user = await self.auth_repo.get_user_by_id(user_id)
        if user and user.stripe_customer_id != customer_id:
            user.stripe_customer_id = customer_id
            await self.auth_repo.session.flush()

    async def _resolve_user_id(
        self, *, customer_id: str | None, metadata: dict | object | None
    ) -> str | None:
        """Resolve our internal user_id from Stripe customer_id or event metadata."""
        uid = _stripe_get(metadata, "user_id")
        if uid:
            return uid

        if customer_id:
            from sqlalchemy import select
            from src.models.auth import User

            result = await self.auth_repo.session.execute(
                select(User.id).where(User.stripe_customer_id == customer_id)
            )
            row = result.scalar_one_or_none()
            if row:
                return row
        return None

    async def _apply_premium(self, user_id: str) -> None:
        await self.ai_detection_repo.update_user_limits(
            user_id=user_id,
            daily_limit=PREMIUM_DAILY_LIMIT,
            monthly_limit=PREMIUM_MONTHLY_LIMIT,
            is_premium=True,
        )

    async def _apply_free(self, user_id: str) -> None:
        await self.ai_detection_repo.update_user_limits(
            user_id=user_id,
            daily_limit=FREE_DAILY_LIMIT,
            monthly_limit=FREE_MONTHLY_LIMIT,
            is_premium=False,
        )


def _ts_to_dt(ts: int | None) -> datetime | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc)
