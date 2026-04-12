"""Generic BeautifulSoup main-content extraction for arbitrary HTML pages."""

from __future__ import annotations

from bs4 import BeautifulSoup

from src.services.url_extraction.constants import (
    CONTENT_TEXT_TAGS,
    GENERIC_MAIN_ROOT_SELECTORS,
    GENERIC_REMOVE_SELECTORS,
    NOISY_TAG_NAMES,
)


def _collapse_ws(text: str) -> str:
    lines = [ln.strip() for ln in text.splitlines()]
    return "\n".join(ln for ln in lines if ln).strip()


def _extract_title(soup: BeautifulSoup) -> str | None:
    h1 = soup.find("h1")
    if h1:
        t = h1.get_text(" ", strip=True)
        if t:
            return t
    og = soup.find("meta", property="og:title")
    if og and og.get("content"):
        return og["content"].strip()
    title = soup.find("title")
    if title:
        t = title.get_text(" ", strip=True)
        if t:
            return t
    return None


def _decompose_noise_global(soup: BeautifulSoup) -> None:
    for name in NOISY_TAG_NAMES:
        for tag in list(soup.find_all(name)):
            tag.decompose()


def _pick_main_root(soup: BeautifulSoup):
    for sel in GENERIC_MAIN_ROOT_SELECTORS:
        node = soup.select_one(sel)
        if node:
            return node
    return soup.body


def _strip_inside_root(root) -> None:
    for sel in GENERIC_REMOVE_SELECTORS:
        for tag in list(root.select(sel)):
            tag.decompose()


def _collect_content_text(root) -> str:
    parts: list[str] = []
    for tag in root.find_all(list(CONTENT_TEXT_TAGS)):
        t = tag.get_text(" ", strip=True)
        if len(t) >= 2:
            parts.append(t)
    return "\n\n".join(parts)


def extract_generic_text(html: str, url: str) -> tuple[str, str | None]:
    """
    Parse downloaded HTML and return (plain_text, title_hint).

    ``url`` is reserved for future per-domain tuning; unused for now.
    """
    _ = url
    soup = BeautifulSoup(html, "lxml")
    title = _extract_title(soup)
    _decompose_noise_global(soup)
    root = _pick_main_root(soup)
    if root is None:
        return "", title
    _strip_inside_root(root)
    text = _collect_content_text(root)
    return _collapse_ws(text), title
