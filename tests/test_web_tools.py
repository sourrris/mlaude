from __future__ import annotations

import json
from types import SimpleNamespace

from mlaude.tools import web_tools


class FakeBackend(web_tools.SearchBackend):
    def __init__(self, name: str, available: bool, results: list[dict]):
        super().__init__(name=name)
        self.available = available
        self.results = results

    def is_available(self) -> bool:
        return self.available

    def search(self, query: str, max_results: int, domains=None, freshness_days=None):
        del query, max_results, domains, freshness_days
        return self.results


def test_web_search_prefers_first_available_backend(monkeypatch) -> None:
    monkeypatch.setattr(
        web_tools,
        "_search_backends",
        lambda: [
            FakeBackend("brave", True, [{"title": "A", "url": "https://a.com", "snippet": "x", "rank": 1, "backend": "brave"}]),
            FakeBackend("duckduckgo", True, []),
        ],
    )

    result = json.loads(web_tools._web_search("latest thing"))
    assert result["backend"] == "brave"
    assert result["results"][0]["url"] == "https://a.com"


def test_domain_filtering_and_ranking() -> None:
    results = web_tools._filter_and_rank_results(
        [
            {"title": "One", "url": "https://docs.example.com/a", "snippet": "a"},
            {"title": "Two", "url": "https://other.com/b", "snippet": "b"},
        ],
        backend="duckduckgo",
        domains=["example.com"],
        max_results=5,
    )
    assert results == [
        {
            "title": "One",
            "url": "https://docs.example.com/a",
            "snippet": "a",
            "rank": 1,
            "backend": "duckduckgo",
        }
    ]


def test_web_extract_returns_metadata(monkeypatch) -> None:
    raw_html = """
    <html>
      <head>
        <title>Doc Page</title>
        <link rel="canonical" href="https://example.com/canonical" />
        <meta property="article:published_time" content="2026-05-01" />
      </head>
      <body><main><p>Hello world</p></main></body>
    </html>
    """

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, url: str, headers=None):
            del headers
            return SimpleNamespace(
                text=raw_html,
                url=url,
                raise_for_status=lambda: None,
            )

    import httpx

    monkeypatch.setattr(httpx, "Client", FakeClient)
    result = json.loads(web_tools._web_extract("https://example.com/page"))
    assert result["title"] == "Doc Page"
    assert result["canonical_url"] == "https://example.com/canonical"
    assert result["published_at"] == "2026-05-01"
    assert "Hello world" in result["content"]
