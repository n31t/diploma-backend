"""
Exchange Google authorization codes and verify ID tokens (server-side only).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import httpx
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token

from src.core.config import Config
from src.core.google_oauth_error import (
    GoogleOAuthError,
    INVALID_GOOGLE_CODE,
)
from src.core.logging import get_logger

logger = get_logger(__name__)

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"


@dataclass(frozen=True)
class GoogleOAuthProfile:
    sub: str
    email: str
    email_verified: bool
    name: str | None = None


def _verify_id_token_sync(id_token_str: str, audience: str) -> dict:
    return google_id_token.verify_oauth2_token(
        id_token_str,
        google_requests.Request(),
        audience,
    )


class GoogleOAuthClient:
    """Real Google OAuth token exchange + ID token verification."""

    def __init__(self, config: Config):
        self._config = config

    async def exchange_code_for_profile(
        self, *, code: str, redirect_uri: str
    ) -> GoogleOAuthProfile:
        client_id = (self._config.GOOGLE_CLIENT_ID or "").strip()
        client_secret = (self._config.GOOGLE_CLIENT_SECRET or "").strip()
        if not client_id or not client_secret:
            raise GoogleOAuthError(
                INVALID_GOOGLE_CODE,
                "Google OAuth is not configured on the server",
            )

        data = {
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                GOOGLE_TOKEN_URL,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

        try:
            payload = response.json()
        except Exception as exc:
            logger.warning("google_token_response_not_json", status=response.status_code)
            raise GoogleOAuthError(
                INVALID_GOOGLE_CODE,
                "Invalid response from Google token endpoint",
            ) from exc

        if response.status_code != 200 or payload.get("error"):
            logger.warning(
                "google_token_exchange_failed",
                status=response.status_code,
                error=payload.get("error"),
            )
            raise GoogleOAuthError(
                INVALID_GOOGLE_CODE,
                "Invalid or expired authorization code",
            )

        id_token_str = payload.get("id_token")
        if not id_token_str or not isinstance(id_token_str, str):
            logger.warning("google_token_missing_id_token")
            raise GoogleOAuthError(
                INVALID_GOOGLE_CODE,
                "Google did not return an ID token",
            )

        try:
            idinfo = await asyncio.to_thread(
                _verify_id_token_sync, id_token_str, client_id
            )
        except ValueError as e:
            logger.warning("google_id_token_verify_failed", error=str(e))
            raise GoogleOAuthError(
                INVALID_GOOGLE_CODE,
                "Could not verify Google identity",
            ) from e

        sub = idinfo.get("sub")
        email = idinfo.get("email")
        if not sub or not email:
            raise GoogleOAuthError(
                INVALID_GOOGLE_CODE,
                "Google token missing required identity fields",
            )

        email_verified = bool(idinfo.get("email_verified", False))
        name = idinfo.get("name")
        if isinstance(name, str):
            name = name.strip() or None
        else:
            name = None

        return GoogleOAuthProfile(
            sub=str(sub),
            email=str(email).strip().lower(),
            email_verified=email_verified,
            name=name,
        )
