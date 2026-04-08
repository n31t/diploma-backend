"""Google OAuth login: AuthService with mocked repository and Google client."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.google_oauth_error import (
    GoogleOAuthError,
    ACCOUNT_INACTIVE,
    GOOGLE_EMAIL_NOT_VERIFIED,
    GOOGLE_OAUTH_DISABLED,
    INVALID_REDIRECT_URI,
    OAUTH_ACCOUNT_CONFLICT,
)
from src.services.auth_service import AuthService, PROVIDER_GOOGLE
from src.services.email_service import EmailService
from src.services.google_oauth_client import GoogleOAuthProfile


def _oauth_config():
    m = MagicMock()
    m.GOOGLE_OAUTH_ENABLED = True
    m.GOOGLE_CLIENT_ID = "test-client-id.apps.googleusercontent.com"
    m.GOOGLE_CLIENT_SECRET = "test-secret"
    m.GOOGLE_ALLOWED_REDIRECT_URIS = "postmessage"
    m.google_allowed_redirect_uri_list = ["postmessage"]
    m.REFRESH_TOKEN_EXPIRE_DAYS = 7
    m.SECRET_KEY = "unit-test-secret-key-at-least-32-characters-long"
    m.ALGORITHM = "HS256"
    m.ACCESS_TOKEN_EXPIRE_MINUTES = 30
    return m


@pytest.fixture
def mock_repo():
    return AsyncMock()


@pytest.fixture
def mock_google() -> MagicMock:
    g = MagicMock()
    g.exchange_code_for_profile = AsyncMock()
    return g


@pytest.fixture
def auth_service(mock_repo, mock_google):
    email = MagicMock(spec=EmailService)
    return AuthService(mock_repo, _oauth_config(), email, mock_google)


@pytest.mark.asyncio
async def test_google_disabled_raises(auth_service, mock_google):
    auth_service.config.GOOGLE_OAUTH_ENABLED = False
    with pytest.raises(GoogleOAuthError) as ei:
        await auth_service.login_with_google_code("c", "postmessage", None, None)
    assert ei.value.code == GOOGLE_OAUTH_DISABLED
    mock_google.exchange_code_for_profile.assert_not_called()


@pytest.mark.asyncio
async def test_google_rejects_unverified_email(auth_service, mock_google):
    mock_google.exchange_code_for_profile.return_value = GoogleOAuthProfile(
        sub="s1",
        email="u@example.com",
        email_verified=False,
    )
    with pytest.raises(GoogleOAuthError) as ei:
        await auth_service.login_with_google_code("c", "postmessage", None, None)
    assert ei.value.code == GOOGLE_EMAIL_NOT_VERIFIED


@pytest.mark.asyncio
async def test_google_new_user_creates_account_and_tokens(
    auth_service, mock_repo, mock_google
):
    mock_google.exchange_code_for_profile.return_value = GoogleOAuthProfile(
        sub="google-sub-1",
        email="new@example.com",
        email_verified=True,
        name="New User",
    )
    mock_repo.get_oauth_account.return_value = None
    mock_repo.get_user_by_email_case_insensitive.return_value = None
    mock_repo.generate_unique_username_from_email.return_value = "newuser"

    new_user = MagicMock()
    new_user.id = "01ARZ3NDEKTSV4RRFFQ69G5FAV"
    new_user.username = "newuser"
    new_user.is_active = True
    mock_repo.create_user.return_value = new_user

    tokens = await auth_service.login_with_google_code("code", "postmessage", None, None)

    assert tokens.access_token
    assert tokens.refresh_token
    mock_repo.create_user.assert_awaited_once()
    cu = mock_repo.create_user.await_args.kwargs
    assert cu["email"] == "new@example.com"
    assert cu["hashed_password"] is None
    assert cu["is_verified"] is True
    mock_repo.create_oauth_account.assert_awaited_once_with(
        user_id=new_user.id,
        provider=PROVIDER_GOOGLE,
        provider_user_id="google-sub-1",
        email="new@example.com",
    )
    mock_repo.create_refresh_token.assert_awaited_once()


@pytest.mark.asyncio
async def test_google_existing_link_logs_in(auth_service, mock_repo, mock_google):
    mock_google.exchange_code_for_profile.return_value = GoogleOAuthProfile(
        sub="same-sub",
        email="old@example.com",
        email_verified=True,
    )
    link = MagicMock()
    link.user_id = "user-1"
    mock_repo.get_oauth_account.return_value = link
    user = MagicMock()
    user.id = "user-1"
    user.username = "olduser"
    user.is_active = True
    mock_repo.get_user_by_id.return_value = user

    await auth_service.login_with_google_code("c", "postmessage", None, None)

    mock_repo.create_user.assert_not_called()
    mock_repo.create_oauth_account.assert_not_called()
    mock_repo.create_refresh_token.assert_awaited_once()


@pytest.mark.asyncio
async def test_google_links_existing_email_user(auth_service, mock_repo, mock_google):
    mock_google.exchange_code_for_profile.return_value = GoogleOAuthProfile(
        sub="g-new",
        email="existing@example.com",
        email_verified=True,
    )
    mock_repo.get_oauth_account.return_value = None
    existing = MagicMock()
    existing.id = "u-existing"
    existing.is_verified = False
    mock_repo.get_user_by_email_case_insensitive.return_value = existing
    mock_repo.get_google_oauth_for_user.return_value = None
    u = MagicMock()
    u.id = "u-existing"
    u.username = "existinguser"
    u.is_active = True
    mock_repo.get_user_by_id.return_value = u

    await auth_service.login_with_google_code("c", "postmessage", None, None)

    mock_repo.create_user.assert_not_called()
    mock_repo.create_oauth_account.assert_awaited_once()
    mock_repo.set_user_verified.assert_awaited_once_with("u-existing")


@pytest.mark.asyncio
async def test_google_conflict_when_email_has_other_google(
    auth_service, mock_repo, mock_google
):
    mock_google.exchange_code_for_profile.return_value = GoogleOAuthProfile(
        sub="g-b",
        email="x@example.com",
        email_verified=True,
    )
    mock_repo.get_oauth_account.return_value = None
    existing = MagicMock()
    existing.id = "u1"
    mock_repo.get_user_by_email_case_insensitive.return_value = existing
    other = MagicMock()
    other.provider_user_id = "g-a"
    mock_repo.get_google_oauth_for_user.return_value = other

    with pytest.raises(GoogleOAuthError) as ei:
        await auth_service.login_with_google_code("c", "postmessage", None, None)
    assert ei.value.code == OAUTH_ACCOUNT_CONFLICT


@pytest.mark.asyncio
async def test_google_link_skips_create_oauth_if_already_linked(
    auth_service, mock_repo, mock_google
):
    """Same Google sub as stored on user — should be handled by oauth lookup first."""
    mock_google.exchange_code_for_profile.return_value = GoogleOAuthProfile(
        sub="g1",
        email="e@example.com",
        email_verified=True,
    )
    link = MagicMock()
    link.user_id = "u1"
    mock_repo.get_oauth_account.return_value = link
    user = MagicMock()
    user.id = "u1"
    user.username = "linkeduser"
    user.is_active = True
    mock_repo.get_user_by_id.return_value = user

    await auth_service.login_with_google_code("c", "postmessage", None, None)

    mock_repo.create_oauth_account.assert_not_called()


@pytest.mark.asyncio
async def test_google_invalid_redirect_uri(auth_service, mock_google):
    with pytest.raises(GoogleOAuthError) as ei:
        await auth_service.login_with_google_code("c", "https://evil/cb", None, None)
    assert ei.value.code == INVALID_REDIRECT_URI
    mock_google.exchange_code_for_profile.assert_not_called()


@pytest.mark.asyncio
async def test_google_inactive_user_rejected(auth_service, mock_repo, mock_google):
    mock_google.exchange_code_for_profile.return_value = GoogleOAuthProfile(
        sub="s1",
        email="in@example.com",
        email_verified=True,
    )
    link = MagicMock()
    link.user_id = "u-in"
    mock_repo.get_oauth_account.return_value = link
    user = MagicMock()
    user.id = "u-in"
    user.is_active = False
    mock_repo.get_user_by_id.return_value = user

    with pytest.raises(GoogleOAuthError) as ei:
        await auth_service.login_with_google_code("c", "postmessage", None, None)
    assert ei.value.code == ACCOUNT_INACTIVE
