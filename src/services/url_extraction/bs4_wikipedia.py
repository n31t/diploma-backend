"""Wikipedia-specific BeautifulSoup extraction."""

from __future__ import annotations

from bs4 import BeautifulSoup

from src.services.url_extraction.constants import (
    CONTENT_TEXT_TAGS,
    NOISY_TAG_NAMES,
    WIKIPEDIA_REMOVE_SELECTORS,
)


def _collapse_ws(text: str) -> str:
    lines = [ln.strip() for ln in text.splitlines()]
    return "\n".join(ln for ln in lines if ln).strip()


def _extract_title(soup: BeautifulSoup) -> str | None:
    h1 = soup.find("h1", id="firstHeading") or soup.find("h1", class_="firstHeading")
    if h1:
        t = h1.get_text(" ", strip=True)
        if t:
            return t
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
        return title.get_text(" ", strip=True) or None
    return None


def _decompose_noise_global(soup: BeautifulSoup) -> None:
    for name in NOISY_TAG_NAMES:
        for tag in list(soup.find_all(name)):
            tag.decompose()


def _strip_wikipedia_noise(root) -> None:
    for sel in WIKIPEDIA_REMOVE_SELECTORS:
        for tag in list(root.select(sel)):
            tag.decompose()


def _collect_content_text(root) -> str:
    parts: list[str] = []
    for tag in root.find_all(list(CONTENT_TEXT_TAGS)):
        t = tag.get_text(" ", strip=True)
        if len(t) >= 2:
            parts.append(t)
    return "\n\n".join(parts)


def extract_wikipedia_text(html: str, url: str) -> tuple[str, str | None]:
    """
    Extract readable article text from Wikipedia HTML.

    Uses #mw-content-text or .mw-parser-output, then strips Wikipedia chrome.
    """
    _ = url
    soup = BeautifulSoup(html, "lxml")
    title = _extract_title(soup)
    _decompose_noise_global(soup)
    root = soup.select_one("#mw-content-text") or soup.select_one(".mw-parser-output")
    if root is None:
        return "", title
    _strip_wikipedia_noise(root)
    text = _collect_content_text(root)
    return _collapse_ws(text), title
