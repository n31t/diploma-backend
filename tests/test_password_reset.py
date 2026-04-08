"""Password reset flow: AuthService with mocked repository and email."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.password_reset_error import (
    PasswordResetError,
    RESET_TOKEN_EXPIRED,
    RESET_TOKEN_INVALID,
    RESET_TOKEN_USED,
)
from src.core.security import hash_password_reset_token, verify_password
from src.services.auth_service import AuthService


@pytest.fixture
def mock_config():
    c = MagicMock()
    c.PASSWORD_RESET_TOKEN_EXPIRE_HOURS = 24
    c.EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS = 48
    return c


@pytest.fixture
def mock_repo():
    return AsyncMock()


@pytest.fixture
def mock_email():
    return AsyncMock()


@pytest.fixture
def auth_service(mock_repo, mock_config, mock_email):
    return AuthService(mock_repo, mock_config, mock_email)


def _future_row(**overrides):
    row = MagicMock()
    row.id = "01ARZ3NDEKTSV4RRFFQ69G5FAV"
    row.user_id = "01ARZ3NDEKTSV4RRFFQ69G5FAW"
    row.is_used = False
    row.expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    for k, v in overrides.items():
        setattr(row, k, v)
    return row


@pytest.mark.asyncio
async def test_request_password_reset_unknown_email_no_side_effects(
    auth_service, mock_repo, mock_email
):
    mock_repo.get_user_by_email_case_insensitive.return_value = None

    await auth_service.request_password_reset("nobody@example.com")

    mock_repo.get_user_by_email_case_insensitive.assert_awaited_once()
    mock_email.send_password_reset_email.assert_not_called()
    mock_repo.create_password_reset_token.assert_not_called()


@pytest.mark.asyncio
async def test_request_password_reset_sends_email_and_creates_token(
    auth_service, mock_repo, mock_email
):
    user = MagicMock()
    user.id = "uid1"
    user.email = "u@example.com"
    user.username = "alice"
    mock_repo.get_user_by_email_case_insensitive.return_value = user

    await auth_service.request_password_reset("Alice@Example.com")

    mock_repo.invalidate_unused_password_reset_tokens_for_user.assert_awaited_once_with(
        "uid1"
    )
    mock_repo.create_password_reset_token.assert_awaited_once()
    create_kw = mock_repo.create_password_reset_token.await_args.kwargs
    assert create_kw["user_id"] == "uid1"
    mail_kw = mock_email.send_password_reset_email.await_args.kwargs
    assert mail_kw["to"] == "u@example.com"
    assert mail_kw["username"] == "alice"
    assert len(mail_kw["token"]) > 10
    assert create_kw["token_hash"] == hash_password_reset_token(mail_kw["token"])


@pytest.mark.asyncio
async def test_validate_token_valid(auth_service, mock_repo):
    raw = "test-raw-token-value"
    th = hash_password_reset_token(raw)
    mock_repo.get_password_reset_token_by_hash.return_value = _future_row()

    valid, code = await auth_service.validate_password_reset_token(raw)

    assert valid is True
    assert code is None
    mock_repo.get_password_reset_token_by_hash.assert_awaited_once_with(th)


@pytest.mark.asyncio
async def test_validate_token_invalid(auth_service, mock_repo):
    mock_repo.get_password_reset_token_by_hash.return_value = None

    valid, code = await auth_service.validate_password_reset_token("x")

    assert valid is False
    assert code == RESET_TOKEN_INVALID


@pytest.mark.asyncio
async def test_validate_token_used(auth_service, mock_repo):
    mock_repo.get_password_reset_token_by_hash.return_value = _future_row(
        is_used=True
    )

    valid, code = await auth_service.validate_password_reset_token("t")

    assert valid is False
    assert code == RESET_TOKEN_USED


@pytest.mark.asyncio
async def test_validate_token_expired(auth_service, mock_repo):
    mock_repo.get_password_reset_token_by_hash.return_value = _future_row(
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=1)
    )

    valid, code = await auth_service.validate_password_reset_token("t")

    assert valid is False
    assert code == RESET_TOKEN_EXPIRED


@pytest.mark.asyncio
async def test_reset_password_success(auth_service, mock_repo):
    raw = "reset-secret-token"
    new_pw = "StrongPass1"
    row = _future_row()
    mock_repo.get_password_reset_token_by_hash.return_value = row

    await auth_service.reset_password(raw, new_pw)

    mock_repo.update_user_password_hash.assert_awaited_once()
    u_call = mock_repo.update_user_password_hash.await_args
    assert u_call.args[0] == row.user_id
    assert verify_password(new_pw, u_call.args[1])
    mock_repo.mark_password_reset_token_used.assert_awaited_once_with(row.id)
    mock_repo.invalidate_unused_password_reset_tokens_for_user.assert_awaited_once_with(
        row.user_id
    )
    mock_repo.revoke_all_refresh_tokens_for_user.assert_awaited_once_with(row.user_id)


@pytest.mark.asyncio
async def test_reset_password_invalid_token_raises(auth_service, mock_repo):
    mock_repo.get_password_reset_token_by_hash.return_value = None

    with pytest.raises(PasswordResetError) as ei:
        await auth_service.reset_password("bad", "StrongPass1")
    assert ei.value.code == RESET_TOKEN_INVALID


@pytest.mark.asyncio
async def test_reset_password_used_token_raises(auth_service, mock_repo):
    mock_repo.get_password_reset_token_by_hash.return_value = _future_row(
        is_used=True
    )

    with pytest.raises(PasswordResetError) as ei:
        await auth_service.reset_password("t", "StrongPass1")
    assert ei.value.code == RESET_TOKEN_USED


@pytest.mark.asyncio
async def test_reset_password_expired_raises(auth_service, mock_repo):
    mock_repo.get_password_reset_token_by_hash.return_value = _future_row(
        expires_at=datetime.now(timezone.utc) - timedelta(seconds=1)
    )

    with pytest.raises(PasswordResetError) as ei:
        await auth_service.reset_password("t", "StrongPass1")
    assert ei.value.code == RESET_TOKEN_EXPIRED


def test_hash_password_reset_token_deterministic():
    assert hash_password_reset_token("abc") == hash_password_reset_token("abc")
    assert len(hash_password_reset_token("abc")) == 64
