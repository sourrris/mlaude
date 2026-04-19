from __future__ import annotations

import pytest

from mlaude.tools import web_search


def test_canonicalize_url_strips_tracking_and_normalizes() -> None:
    assert (
        web_search.canonicalize_url(
            "https://www.example.com/path/?utm_source=test&b=2&a=1"
        )
        == "https://example.com/path?a=1&b=2"
    )


def test_extract_page_content_uses_html_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(web_search, "trafilatura", None)
    monkeypatch.setattr(web_search, "Document", None)

    extracted = web_search.extract_page_content(
        "<html><body><h1>Launch Window</h1><p>Window opens at 14:00 UTC.</p></body></html>",
        "https://example.com/post",
    )

    assert extracted["extract_status"] == "html_fallback"
    assert "Launch Window" in extracted["content"]
    assert "14:00 UTC" in extracted["content"]


@pytest.mark.asyncio
async def test_search_web_normalizes_hits(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeDDGS:
        def __enter__(self) -> "FakeDDGS":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
            return None

        def text(self, query: str, max_results: int = 5):  # noqa: ARG002
            return [
                {
                    "title": "Result A",
                    "href": "https://www.example.com/path/?utm_source=test",
                    "body": "Fresh result",
                },
                {
                    "title": "Result A Duplicate",
                    "href": "https://example.com/path",
                    "body": "Duplicate",
                },
            ]

    monkeypatch.setattr(web_search, "DDGS", FakeDDGS)

    results = await web_search.search_web("launch window", max_results=5)

    assert len(results) == 1
    assert results[0]["source_kind"] == "web_result"
    assert results[0]["source"] == "https://example.com/path"
    assert results[0]["extract_status"] == "not_fetched"
