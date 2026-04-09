"""
Tests for programmatic subscription cancel/resume (Stripe API initiation only).
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import stripe as stripe_lib

from src.core.billing_exceptions import BillingServiceError
from src.services.stripe_service import StripeService


def _make_config(**overrides):
    cfg = MagicMock()
    cfg.STRIPE_SECRET_KEY = "sk_test_fake"
    cfg.STRIPE_WEBHOOK_SECRET = "whsec_fake"
    cfg.STRIPE_PRICE_ID = "price_fake"
    cfg.FRONTEND_URL = "http://localhost:3000"
    for k, v in overrides.items():
        setattr(cfg, k, v)
    return cfg


@pytest.fixture
def mock_subscription_repo():
    return AsyncMock()


@pytest.fixture
def mock_ai_detection_repo():
    return AsyncMock()


@pytest.fixture
def mock_auth_repo():
    repo = AsyncMock()
    user = MagicMock()
    user.id = "user_01"
    user.stripe_customer_id = "cus_123"
    repo.get_user_by_id.return_value = user
    repo.session = AsyncMock()
    return repo


@pytest.fixture
def stripe_service(mock_subscription_repo, mock_ai_detection_repo, mock_auth_repo):
    return StripeService(
        config=_make_config(),
        subscription_repo=mock_subscription_repo,
        ai_detection_repo=mock_ai_detection_repo,
        auth_repo=mock_auth_repo,
    )


@pytest.mark.asyncio
class TestCancelSubscriptionForUser:
    async def test_calls_stripe_modify_cancel_at_period_end(
        self, stripe_service, mock_subscription_repo
    ):
        sub = MagicMock()
        sub.stripe_subscription_id = "sub_abc"
        sub.status = "active"
        sub.cancel_at_period_end = False
        mock_subscription_repo.get_by_user_id.return_value = sub

        with patch("stripe.Subscription.modify") as mock_modify:
            already = await stripe_service.cancel_subscription_for_user("user_01")

        assert already is False
        mock_modify.assert_called_once_with("sub_abc", cancel_at_period_end=True)

    async def test_no_subscription_raises(self, stripe_service, mock_subscription_repo):
        mock_subscription_repo.get_by_user_id.return_value = None

        with pytest.raises(BillingServiceError) as exc_info:
            await stripe_service.cancel_subscription_for_user("user_01")
        assert exc_info.value.code == "NO_ACTIVE_SUBSCRIPTION"

    async def test_inactive_status_raises(self, stripe_service, mock_subscription_repo):
        sub = MagicMock()
        sub.status = "canceled"
        sub.cancel_at_period_end = True
        mock_subscription_repo.get_by_user_id.return_value = sub

        with pytest.raises(BillingServiceError) as exc_info:
            await stripe_service.cancel_subscription_for_user("user_01")
        assert exc_info.value.code == "NO_ACTIVE_SUBSCRIPTION"

    async def test_already_scheduled_idempotent_no_stripe_call(
        self, stripe_service, mock_subscription_repo
    ):
        sub = MagicMock()
        sub.stripe_subscription_id = "sub_abc"
        sub.status = "active"
        sub.cancel_at_period_end = True
        mock_subscription_repo.get_by_user_id.return_value = sub

        with patch("stripe.Subscription.modify") as mock_modify:
            already = await stripe_service.cancel_subscription_for_user("user_01")

        assert already is True
        mock_modify.assert_not_called()

    async def test_stripe_error_wrapped(self, stripe_service, mock_subscription_repo):
        sub = MagicMock()
        sub.stripe_subscription_id = "sub_abc"
        sub.status = "active"
        sub.cancel_at_period_end = False
        mock_subscription_repo.get_by_user_id.return_value = sub

        with patch(
            "stripe.Subscription.modify",
            side_effect=stripe_lib.error.InvalidRequestError("bad", "param"),
        ):
            with pytest.raises(BillingServiceError) as exc_info:
                await stripe_service.cancel_subscription_for_user("user_01")
        assert exc_info.value.code == "STRIPE_REQUEST_FAILED"
        assert exc_info.value.http_status == 502

    async def test_no_secret_key_raises(self, mock_subscription_repo, mock_ai_detection_repo, mock_auth_repo):
        svc = StripeService(
            config=_make_config(STRIPE_SECRET_KEY=None),
            subscription_repo=mock_subscription_repo,
            ai_detection_repo=mock_ai_detection_repo,
            auth_repo=mock_auth_repo,
        )
        with pytest.raises(BillingServiceError) as exc_info:
            await svc.cancel_subscription_for_user("user_01")
        assert exc_info.value.code == "STRIPE_NOT_CONFIGURED"


@pytest.mark.asyncio
class TestResumeSubscriptionForUser:
    async def test_calls_stripe_modify_resume(self, stripe_service, mock_subscription_repo):
        sub = MagicMock()
        sub.stripe_subscription_id = "sub_abc"
        sub.status = "active"
        sub.cancel_at_period_end = True
        mock_subscription_repo.get_by_user_id.return_value = sub

        with patch("stripe.Subscription.modify") as mock_modify:
            await stripe_service.resume_subscription_for_user("user_01")

        mock_modify.assert_called_once_with("sub_abc", cancel_at_period_end=False)

    async def test_not_scheduled_raises(self, stripe_service, mock_subscription_repo):
        sub = MagicMock()
        sub.stripe_subscription_id = "sub_abc"
        sub.status = "active"
        sub.cancel_at_period_end = False
        mock_subscription_repo.get_by_user_id.return_value = sub

        with pytest.raises(BillingServiceError) as exc_info:
            await stripe_service.resume_subscription_for_user("user_01")
        assert exc_info.value.code == "CANCELLATION_NOT_SCHEDULED"
        assert exc_info.value.http_status == 409
