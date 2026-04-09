"""
Pydantic schemas for billing / subscription endpoints.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class CheckoutResponse(BaseModel):
    url: str = Field(..., description="Stripe Checkout redirect URL")


class PortalResponse(BaseModel):
    url: str = Field(..., description="Stripe Customer Portal URL")


class SubscriptionStatusResponse(BaseModel):
    is_premium: bool = Field(..., description="Whether user currently has an active premium subscription")
    status: Optional[str] = Field(None, description="Subscription status (active, past_due, canceled, ...)")
    plan_type: Optional[str] = Field(None, description="Plan type, e.g. 'premium'")
    current_period_end: Optional[datetime] = Field(None, description="End of current billing period")
    cancel_at_period_end: Optional[bool] = Field(None, description="Whether subscription will cancel at period end")
    stripe_subscription_id: Optional[str] = Field(
        None,
        description="Stripe subscription id (present when a subscription row exists)",
    )


class BillingActionResponse(BaseModel):
    status: str = Field(default="ok", description="Outcome marker")
    message: str = Field(..., description="Human-readable result")
    sync_pending: bool = Field(
        True,
        description="True until Stripe webhooks have updated local subscription state",
    )
    already_scheduled: bool = Field(
        False,
        description="True when cancellation was already scheduled (idempotent cancel)",
    )
