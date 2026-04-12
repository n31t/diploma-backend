"""Tests for URL HTML extraction (quality gates, BS4, NewspaperService orchestration)."""

from __future__ import annotations

import pytest

from src.dtos.ai_detection_dto import NewspaperFetchResultDTO
from src.services.newspaper_service import DownloadedHtml, NewspaperService
from src.services.url_extraction.constants import MAX_HTML_TEXT_LENGTH
from src.services.url_extraction.domain import is_wikipedia_host, parsed_host
from src.services.url_extraction.quality import evaluate_text_quality
from src.services.url_extraction.bs4_generic import extract_generic_text
from src.services.url_extraction.bs4_wikipedia import extract_wikipedia_text


def _long_paragraph() -> str:
    return (
        "Lorem ipsum dolor sit amet, consectetur adipiscing elit. " * 5
        + "Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. " * 5
    )


def _html_article_main() -> str:
    body = "".join(f"<p>{_long_paragraph()}</p>" for _ in range(5))
    return f"""<!DOCTYPE html><html><head><title>Article Title</title></head>
    <body><nav>skip</nav><article>{body}</article></body></html>"""


def _html_wikipedia() -> str:
    paras = "".join(f"<p>{_long_paragraph()}</p>" for _ in range(5))
    return f"""<!DOCTYPE html><html><head><title>Wiki — Topic</title></head><body>
    <div id="mw-content-text" class="mw-parser-output">
    <div class="infobox">noise</div>
    <table><tr><td>x</td></tr></table>
    <div class="toc">toc</div>
    <h1 class="firstHeading" id="firstHeading">Article subject</h1>
    {paras}
    <div class="reflist">refs</div>
    </div></body></html>"""


class TestQualityEvaluation:
    def test_rejects_too_short(self) -> None:
        r = evaluate_text_quality("short")
        assert not r.accepted
        assert r.rejection_reason == "too_few_chars"

    def test_accepts_substantial_text(self) -> None:
        text = "\n\n".join(_long_paragraph() for _ in range(6))
        r = evaluate_text_quality(text)
        assert r.accepted
        assert r.rejection_reason is None


class TestDomain:
    def test_wikipedia_hosts(self) -> None:
        assert is_wikipedia_host("en.wikipedia.org")
        assert is_wikipedia_host("ru.wikipedia.org")
        assert is_wikipedia_host("en.m.wikipedia.org")
        assert not is_wikipedia_host("example.com")

    def test_parsed_host(self) -> None:
        assert parsed_host("https://EN.WIKIPEDIA.org/wiki/X") == "en.wikipedia.org"


class TestBs4Extractors:
    def test_generic_extracts_main(self) -> None:
        html = _html_article_main()
        text, title = extract_generic_text(html, "https://example.com/a")
        assert title == "Article Title"
        assert "Lorem ipsum" in text
        r = evaluate_text_quality(text)
        assert r.accepted

    def test_wikipedia_extract(self) -> None:
        html = _html_wikipedia()
        text, title = extract_wikipedia_text(html, "https://en.wikipedia.org/wiki/Test")
        assert title == "Article subject"
        assert "infobox" not in text.lower()
        r = evaluate_text_quality(text)
        assert r.accepted


@pytest.mark.asyncio
class TestNewspaperServiceOrchestration:
    async def test_single_download_no_duplicate_fetch(self, monkeypatch: pytest.MonkeyPatch) -> None:
        html = _html_article_main()
        calls: list[int] = []

        async def track_download(self, url: str) -> DownloadedHtml:
            calls.append(1)
            return DownloadedHtml(
                content=html,
                truncated=False,
                original_text_length=len(html),
            )

        monkeypatch.setattr(NewspaperService, "_download_html", track_download)

        def bad_newspaper(url: str, raw: str) -> NewspaperFetchResultDTO:
            return NewspaperFetchResultDTO(
                text="tiny",
                url=url,
                title="t",
                authors=[],
                publish_date=None,
            )

        monkeypatch.setattr(
            NewspaperService, "_parse_with_newspaper", staticmethod(bad_newspaper)
        )

        svc = NewspaperService()
        dto = await svc.fetch_article("https://example.com/news/1")
        assert len(calls) == 1
        assert dto.extraction_method == "bs4_generic"
        assert dto.fallback_used is True
        assert "Lorem ipsum" in dto.text

    async def test_newspaper_success_no_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        html = "<html><body><p>x</p></body></html>"

        async def dl(self, url: str) -> DownloadedHtml:
            return DownloadedHtml(
                content=html,
                truncated=False,
                original_text_length=len(html),
            )

        monkeypatch.setattr(NewspaperService, "_download_html", dl)

        good = "\n\n".join(_long_paragraph() for _ in range(6))

        def good_np(url: str, raw: str) -> NewspaperFetchResultDTO:
            return NewspaperFetchResultDTO(
                text=good,
                url=url,
                title="OK",
                authors=["A"],
                publish_date=None,
            )

        monkeypatch.setattr(
            NewspaperService, "_parse_with_newspaper", staticmethod(good_np)
        )

        svc = NewspaperService()
        dto = await svc.fetch_article("https://example.com/p")
        assert dto.extraction_method == "newspaper"
        assert dto.fallback_used is False

    async def test_wikipedia_prefers_bs4_first(self, monkeypatch: pytest.MonkeyPatch) -> None:
        html = _html_wikipedia()

        async def dl(self, url: str) -> DownloadedHtml:
            return DownloadedHtml(
                content=html,
                truncated=False,
                original_text_length=len(html),
            )

        monkeypatch.setattr(NewspaperService, "_download_html", dl)

        def fail_np(url: str, raw: str) -> NewspaperFetchResultDTO:
            raise RuntimeError("should not be needed when wiki bs4 succeeds")

        monkeypatch.setattr(
            NewspaperService, "_parse_with_newspaper", staticmethod(fail_np)
        )

        svc = NewspaperService()
        dto = await svc.fetch_article("https://en.wikipedia.org/wiki/Something")
        assert dto.extraction_method == "bs4_wikipedia"
        assert dto.fallback_used is False

    async def test_all_strategies_fail(self, monkeypatch: pytest.MonkeyPatch) -> None:
        html = "<html><body><p>hi</p></body></html>"

        async def dl(self, url: str) -> DownloadedHtml:
            return DownloadedHtml(
                content=html,
                truncated=False,
                original_text_length=len(html),
            )

        monkeypatch.setattr(NewspaperService, "_download_html", dl)

        def bad_np(url: str, raw: str) -> NewspaperFetchResultDTO:
            return NewspaperFetchResultDTO(
                text="no",
                url=url,
                title=None,
                authors=[],
                publish_date=None,
            )

        monkeypatch.setattr(
            NewspaperService, "_parse_with_newspaper", staticmethod(bad_np)
        )

        svc = NewspaperService()
        with pytest.raises(RuntimeError, match="Could not extract acceptable text"):
            await svc.fetch_article("https://example.com/empty")

    async def test_truncation_flag_propagates(self, monkeypatch: pytest.MonkeyPatch) -> None:
        base = _html_article_main()
        huge = base + ("x" * (MAX_HTML_TEXT_LENGTH + 10))
        content = huge[:MAX_HTML_TEXT_LENGTH]

        async def dl(self, url: str) -> DownloadedHtml:
            return DownloadedHtml(
                content=content,
                truncated=True,
                original_text_length=len(huge),
            )

        monkeypatch.setattr(NewspaperService, "_download_html", dl)

        good = "\n\n".join(_long_paragraph() for _ in range(6))

        def good_np(url: str, raw: str) -> NewspaperFetchResultDTO:
            return NewspaperFetchResultDTO(
                text=good,
                url=url,
                title="T",
                authors=[],
                publish_date=None,
            )

        monkeypatch.setattr(
            NewspaperService, "_parse_with_newspaper", staticmethod(good_np)
        )

        svc = NewspaperService()
        dto = await svc.fetch_article("https://example.com/big")
        assert dto.html_truncated is True
