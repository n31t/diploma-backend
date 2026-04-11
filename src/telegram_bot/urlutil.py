"""Validate URL strings using the same rules as the HTTP API."""

from __future__ import annotations

import ipaddress
from urllib.parse import urlparse

from pydantic import ValidationError

from src.api.v1.schemas.ai_detection import URLDetectionRequest


def url_allowed_for_telegram_inline_button(url: str) -> bool:
    """
    Telegram Bot API rejects many URLs for InlineKeyboardButton.url, e.g. localhost
    (error: Bad Request: Wrong HTTP URL). Use plain text in the message for those.

    Stripe checkout/portal HTTPS URLs are always allowed.
    """
    try:
        p = urlparse(url.strip())
    except Exception:
        return False
    if p.scheme not in ("http", "https"):
        return False
    host = p.hostname
    if not host:
        return False
    h = host.lower().strip("[]")
    if h == "localhost" or h.endswith(".localhost"):
        return False
    try:
        addr = ipaddress.ip_address(h)
        if addr.is_loopback:
            return False
    except ValueError:
        pass
    return True


def validate_public_url(raw: str) -> str:
    """
    Return normalized URL or raise ValueError with API-aligned message.

    Raises:
        ValueError: invalid URL
    """
    try:
        m = URLDetectionRequest.model_validate({"url": raw.strip(), "language": "auto"})
        return m.url
    except ValidationError as e:
        err = e.errors()[0].get("msg", "Invalid URL") if e.errors() else "Invalid URL"
        raise ValueError(str(err)) from e
