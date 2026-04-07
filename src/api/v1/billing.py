"""
Billing / subscription API endpoints.
"""

from typing import Annotated

import stripe
from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Depends, HTTPException, Request, status

from src.api.v1.schemas.billing import (
    CheckoutResponse,
    PortalResponse,
    SubscriptionStatusResponse,
)
from src.core.billing import ACTIVE_SUBSCRIPTION_STATUSES
from src.core.logging import get_logger
from src.dtos.user_dto import AuthenticatedUserDTO
from src.repositories.subscription_repository import SubscriptionRepository
from src.services.shared.auth_helpers import get_authenticated_user_dependency
from src.services.stripe_service import StripeService

logger = get_logger(__name__)

router = APIRouter(prefix="/billing", route_class=DishkaRoute)

# ------------------------------------------------------------------
# Webhook (unauthenticated -- signature-verified by Stripe SDK)
# ------------------------------------------------------------------


@router.post("/webhook", include_in_schema=False)
async def stripe_webhook(request: Request, stripe_service: FromDishka[StripeService]):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    try:
        event = stripe_service.verify_webhook(payload, sig_header)
    except stripe.SignatureVerificationError:
        logger.warning("stripe_webhook_invalid_signature")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid signature")
    except ValueError:
        logger.warning("stripe_webhook_invalid_payload")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid payload")

    await stripe_service.handle_event(event)
    return {"status": "ok"}


# ------------------------------------------------------------------
# Authenticated endpoints
# ------------------------------------------------------------------


@router.post("/checkout", response_model=CheckoutResponse)
async def create_checkout(
    stripe_service: FromDishka[StripeService],
    current_user: Annotated[AuthenticatedUserDTO, Depends(get_authenticated_user_dependency)],
):
    """Create a Stripe Checkout session for a premium subscription."""
    try:
        url = await stripe_service.create_checkout_session(
            user_id=current_user.id, email=current_user.email
        )
    except Exception as exc:
        logger.error("checkout_creation_failed", error=str(exc), user_id=current_user.id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not create checkout session",
        )
    return CheckoutResponse(url=url)


@router.get("/subscription", response_model=SubscriptionStatusResponse)
async def get_subscription_status(
    subscription_repo: FromDishka[SubscriptionRepository],
    current_user: Annotated[AuthenticatedUserDTO, Depends(get_authenticated_user_dependency)],
):
    """Return the current user's subscription status."""
    sub = await subscription_repo.get_by_user_id(current_user.id)
    if sub is None:
        return SubscriptionStatusResponse(is_premium=False)

    return SubscriptionStatusResponse(
        is_premium=sub.status in ACTIVE_SUBSCRIPTION_STATUSES,
        status=sub.status,
        plan_type=sub.plan_type,
        current_period_end=sub.current_period_end,
        cancel_at_period_end=sub.cancel_at_period_end,
    )


@router.post("/portal", response_model=PortalResponse)
async def create_portal(
    stripe_service: FromDishka[StripeService],
    current_user: Annotated[AuthenticatedUserDTO, Depends(get_authenticated_user_dependency)],
):
    """Create a Stripe Customer Portal session for subscription management."""
    try:
        url = await stripe_service.create_portal_session(user_id=current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        logger.error("portal_creation_failed", error=str(exc), user_id=current_user.id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not create portal session",
        )
    return PortalResponse(url=url)
