"""Host / domain helpers for extraction routing."""

from __future__ import annotations

from urllib.parse import urlparse


def parsed_host(url: str) -> str:
    """Return lowercased hostname without port, or empty string."""
    try:
        h = urlparse(url).hostname
    except Exception:
        return ""
    return (h or "").lower().strip()


def is_wikipedia_host(host: str) -> bool:
    """True for Wikipedia content hosts (any language subdomain)."""
    if not host:
        return False
    h = host.lower()
    if h == "wikipedia.org":
        return True
    if h.endswith(".wikipedia.org"):
        return True
    if h.endswith(".m.wikipedia.org"):
        return True
    return False
