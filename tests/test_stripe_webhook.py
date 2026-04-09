"""
Tests for Stripe billing: webhook handling, subscription lifecycle, service logic.
"""

import time
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import stripe as stripe_lib

from src.core.billing import (
    FREE_DAILY_LIMIT,
    FREE_MONTHLY_LIMIT,
    PREMIUM_DAILY_LIMIT,
    PREMIUM_MONTHLY_LIMIT,
)
from src.services.stripe_service import StripeService, _ts_to_dt


def _make_event(event_type: str, event_id: str, data_object: dict):
    """Build a plain MagicMock that looks like a stripe.Event."""
    event = MagicMock()
    event.type = event_type
    event.id = event_id
    event.data.object = data_object
    return event


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

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
    repo = AsyncMock()
    repo.get_by_user_id.return_value = None
    repo.get_by_stripe_subscription_id.return_value = None
    return repo


@pytest.fixture
def mock_ai_detection_repo():
    repo = AsyncMock()
    return repo


@pytest.fixture
def mock_auth_repo():
    repo = AsyncMock()
    user = MagicMock()
    user.id = "user_01"
    user.stripe_customer_id = None
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


# ---------------------------------------------------------------------------
# Unit: _ts_to_dt helper
# ---------------------------------------------------------------------------

class TestTsToDatetime:
    def test_none_returns_none(self):
        assert _ts_to_dt(None) is None

    def test_converts_epoch(self):
        ts = 1700000000
        dt = _ts_to_dt(ts)
        assert isinstance(dt, datetime)
        assert dt.tzinfo is not None
        assert dt == datetime.fromtimestamp(ts, tz=timezone.utc)


# ---------------------------------------------------------------------------
# Unit: webhook signature verification
# ---------------------------------------------------------------------------

class TestWebhookSignatureVerification:
    def test_verify_webhook_valid(self, stripe_service):
        payload = b'{"id": "evt_test"}'
        fake_event = MagicMock()

        with patch("stripe.Webhook.construct_event", return_value=fake_event) as mock_construct:
            event = stripe_service.verify_webhook(payload, "sig_header")
            mock_construct.assert_called_once_with(payload, "sig_header", "whsec_fake")
            assert event is fake_event

    def test_verify_webhook_invalid_signature(self, stripe_service):
        payload = b'{"id": "evt_test"}'

        with patch(
            "stripe.Webhook.construct_event",
            side_effect=stripe_lib.SignatureVerificationError("bad sig", "sig_header"),
        ):
            with pytest.raises(stripe_lib.SignatureVerificationError):
                stripe_service.verify_webhook(payload, "bad_sig")


# ---------------------------------------------------------------------------
# Unit: event dispatch
# ---------------------------------------------------------------------------

class TestEventDispatch:
    @pytest.mark.asyncio
    async def test_unknown_event_is_ignored(self, stripe_service):
        event = _make_event("unknown.event.type", "evt_unknown", {})
        await stripe_service.handle_event(event)

    @pytest.mark.asyncio
    async def test_checkout_completed_creates_subscription(self, stripe_service, mock_subscription_repo, mock_ai_detection_repo):
        period_end = int(time.time()) + 86400 * 30
        sub_obj = {
            "id": "sub_123",
            "status": "active",
            "current_period_end": period_end,
            "cancel_at_period_end": False,
        }

        event = _make_event("checkout.session.completed", "evt_checkout", {
            "id": "cs_123",
            "client_reference_id": "user_01",
            "customer": "cus_123",
            "subscription": "sub_123",
        })

        with patch("stripe.Subscription.retrieve", return_value=sub_obj):
            await stripe_service.handle_event(event)

        mock_subscription_repo.upsert.assert_awaited_once()
        call_kwargs = mock_subscription_repo.upsert.call_args.kwargs
        assert call_kwargs["user_id"] == "user_01"
        assert call_kwargs["stripe_subscription_id"] == "sub_123"
        assert call_kwargs["status"] == "active"

        mock_ai_detection_repo.update_user_limits.assert_awaited_once_with(
            user_id="user_01",
            daily_limit=PREMIUM_DAILY_LIMIT,
            monthly_limit=PREMIUM_MONTHLY_LIMIT,
            is_premium=True,
        )

    @pytest.mark.asyncio
    async def test_subscription_deleted_reverts_to_free(self, stripe_service, mock_subscription_repo, mock_ai_detection_repo, mock_auth_repo):
        event = _make_event("customer.subscription.deleted", "evt_del", {
            "id": "sub_123",
            "customer": "cus_123",
            "status": "canceled",
            "current_period_end": int(time.time()),
            "cancel_at_period_end": True,
            "metadata": {"user_id": "user_01"},
        })

        await stripe_service.handle_event(event)

        mock_subscription_repo.upsert.assert_awaited_once()
        call_kwargs = mock_subscription_repo.upsert.call_args.kwargs
        assert call_kwargs["status"] == "canceled"

        mock_ai_detection_repo.update_user_limits.assert_awaited_once_with(
            user_id="user_01",
            daily_limit=FREE_DAILY_LIMIT,
            monthly_limit=FREE_MONTHLY_LIMIT,
            is_premium=False,
        )


# ---------------------------------------------------------------------------
# Unit: subscription upsert (created / updated)
# ---------------------------------------------------------------------------

class TestSubscriptionUpsert:
    @pytest.mark.asyncio
    async def test_active_subscription_applies_premium(self, stripe_service, mock_subscription_repo, mock_ai_detection_repo):
        event = _make_event("customer.subscription.updated", "evt_upd", {
            "id": "sub_123",
            "customer": "cus_123",
            "status": "active",
            "current_period_end": int(time.time()) + 86400 * 30,
            "cancel_at_period_end": False,
            "metadata": {"user_id": "user_01"},
        })

        await stripe_service.handle_event(event)

        mock_ai_detection_repo.update_user_limits.assert_awaited_once_with(
            user_id="user_01",
            daily_limit=PREMIUM_DAILY_LIMIT,
            monthly_limit=PREMIUM_MONTHLY_LIMIT,
            is_premium=True,
        )

    @pytest.mark.asyncio
    async def test_past_due_subscription_reverts_to_free(self, stripe_service, mock_subscription_repo, mock_ai_detection_repo):
        event = _make_event("customer.subscription.updated", "evt_past", {
            "id": "sub_123",
            "customer": "cus_123",
            "status": "past_due",
            "current_period_end": int(time.time()) + 86400 * 5,
            "cancel_at_period_end": False,
            "metadata": {"user_id": "user_01"},
        })

        await stripe_service.handle_event(event)

        mock_ai_detection_repo.update_user_limits.assert_awaited_once_with(
            user_id="user_01",
            daily_limit=FREE_DAILY_LIMIT,
            monthly_limit=FREE_MONTHLY_LIMIT,
            is_premium=False,
        )

    @pytest.mark.asyncio
    async def test_cancel_at_period_end_true_still_active_keeps_premium(
        self, stripe_service, mock_subscription_repo, mock_ai_detection_repo
    ):
        """Scheduled cancellation: status stays active/trialing — user remains premium until period ends."""
        event = _make_event("customer.subscription.updated", "evt_cancel_sched", {
            "id": "sub_123",
            "customer": "cus_123",
            "status": "active",
            "current_period_end": int(time.time()) + 86400 * 10,
            "cancel_at_period_end": True,
            "metadata": {"user_id": "user_01"},
        })

        await stripe_service.handle_event(event)

        call_kwargs = mock_subscription_repo.upsert.call_args.kwargs
        assert call_kwargs["cancel_at_period_end"] is True

        mock_ai_detection_repo.update_user_limits.assert_awaited_once_with(
            user_id="user_01",
            daily_limit=PREMIUM_DAILY_LIMIT,
            monthly_limit=PREMIUM_MONTHLY_LIMIT,
            is_premium=True,
        )


# ---------------------------------------------------------------------------
# Unit: idempotent replay
# ---------------------------------------------------------------------------

class TestIdempotency:
    @pytest.mark.asyncio
    async def test_replay_checkout_completed_is_safe(self, stripe_service, mock_subscription_repo, mock_ai_detection_repo):
        """Calling checkout.session.completed twice should just upsert again."""
        period_end = int(time.time()) + 86400 * 30
        sub_obj = {
            "id": "sub_123",
            "status": "active",
            "current_period_end": period_end,
            "cancel_at_period_end": False,
        }

        event = _make_event("checkout.session.completed", "evt_checkout", {
            "id": "cs_123",
            "client_reference_id": "user_01",
            "customer": "cus_123",
            "subscription": "sub_123",
        })

        with patch("stripe.Subscription.retrieve", return_value=sub_obj):
            await stripe_service.handle_event(event)
            await stripe_service.handle_event(event)

        assert mock_subscription_repo.upsert.await_count == 2
        assert mock_ai_detection_repo.update_user_limits.await_count == 2


# ---------------------------------------------------------------------------
# Unit: invoice events
# ---------------------------------------------------------------------------

class TestInvoiceEvents:
    @pytest.mark.asyncio
    async def test_invoice_paid_updates_period(self, stripe_service, mock_subscription_repo, mock_ai_detection_repo):
        existing_sub = MagicMock()
        existing_sub.user_id = "user_01"
        mock_subscription_repo.get_by_stripe_subscription_id.return_value = existing_sub

        new_period_end = int(time.time()) + 86400 * 30
        sub_obj = {
            "id": "sub_123",
            "status": "active",
            "current_period_end": new_period_end,
            "cancel_at_period_end": False,
        }

        event = _make_event("invoice.paid", "evt_inv_paid", {
            "id": "in_123",
            "subscription": "sub_123",
            "customer_email": "test@example.com",
        })

        with patch("stripe.Subscription.retrieve", return_value=sub_obj):
            await stripe_service.handle_event(event)

        mock_subscription_repo.upsert.assert_awaited_once()
        mock_ai_detection_repo.update_user_limits.assert_awaited_once_with(
            user_id="user_01",
            daily_limit=PREMIUM_DAILY_LIMIT,
            monthly_limit=PREMIUM_MONTHLY_LIMIT,
            is_premium=True,
        )

    @pytest.mark.asyncio
    async def test_invoice_payment_failed_no_crash(self, stripe_service, mock_ai_detection_repo):
        event = _make_event("invoice.payment_failed", "evt_inv_fail", {
            "id": "in_456",
            "subscription": "sub_123",
            "customer_email": "test@example.com",
        })
        await stripe_service.handle_event(event)
        mock_ai_detection_repo.update_user_limits.assert_not_awaited()


# ---------------------------------------------------------------------------
# Unit: billing constants
# ---------------------------------------------------------------------------

class TestBillingConstants:
    def test_free_limits(self):
        assert FREE_DAILY_LIMIT == 10
        assert FREE_MONTHLY_LIMIT == 100

    def test_premium_limits(self):
        assert PREMIUM_DAILY_LIMIT == 100
        assert PREMIUM_MONTHLY_LIMIT == 1000

    def test_premium_greater_than_free(self):
        assert PREMIUM_DAILY_LIMIT > FREE_DAILY_LIMIT
        assert PREMIUM_MONTHLY_LIMIT > FREE_MONTHLY_LIMIT
