"""Web search and extraction tools with pluggable backends."""

from __future__ import annotations

import html
import os
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

from mlaude.tools.registry import registry, tool_error, tool_result


_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


@dataclass
class SearchBackend:
    name: str

    def is_available(self) -> bool:
        return True

    def search(
        self,
        query: str,
        max_results: int,
        domains: list[str] | None = None,
        freshness_days: int | None = None,
    ) -> list[dict[str, Any]]:
        raise NotImplementedError


class BraveSearchBackend(SearchBackend):
    def __init__(self) -> None:
        super().__init__(name="brave")

    def is_available(self) -> bool:
        return bool(os.environ.get("BRAVE_SEARCH_API_KEY"))

    def search(
        self,
        query: str,
        max_results: int,
        domains: list[str] | None = None,
        freshness_days: int | None = None,
    ) -> list[dict[str, Any]]:
        import httpx

        headers = {
            "Accept": "application/json",
            "X-Subscription-Token": os.environ["BRAVE_SEARCH_API_KEY"],
        }
        params: dict[str, Any] = {"q": query, "count": max_results}
        if freshness_days is not None:
            params["freshness"] = f"{freshness_days}d"

        with httpx.Client(timeout=15.0) as client:
            resp = client.get(
                "https://api.search.brave.com/res/v1/web/search",
                params=params,
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()

        results: list[dict[str, Any]] = []
        for item in data.get("web", {}).get("results", []):
            results.append(
                {
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "snippet": item.get("description", ""),
                }
            )
        return _filter_and_rank_results(results, self.name, domains, max_results)


class DuckDuckGoSearchBackend(SearchBackend):
    def __init__(self) -> None:
        super().__init__(name="duckduckgo")

    def search(
        self,
        query: str,
        max_results: int,
        domains: list[str] | None = None,
        freshness_days: int | None = None,
    ) -> list[dict[str, Any]]:
        import httpx

        del freshness_days
        search_query = _add_domain_filters(query, domains)
        url = f"https://html.duckduckgo.com/html/?q={quote_plus(search_query)}"
        headers = {"User-Agent": _USER_AGENT}

        with httpx.Client(timeout=15.0, follow_redirects=True) as client:
            resp = client.get(url, headers=headers)
            resp.raise_for_status()
            raw_html = resp.text

        results: list[dict[str, Any]] = []
        pattern = re.compile(
            r'<a[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>.*?'
            r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>',
            re.DOTALL,
        )
        for match in pattern.finditer(raw_html):
            if len(results) >= max_results * 2:
                break
            href = _unwrap_duckduckgo_url(match.group(1))
            title = _strip_tags(match.group(2))
            snippet = _strip_tags(match.group(3))
            results.append({"title": title, "url": href, "snippet": snippet})

        return _filter_and_rank_results(results, self.name, domains, max_results)


def _search_backends() -> list[SearchBackend]:
    return [BraveSearchBackend(), DuckDuckGoSearchBackend()]


def _web_search(
    query: str,
    max_results: int = 5,
    domains: list[str] | None = None,
    freshness_days: int | None = None,
    task_id: str | None = None,
) -> str:
    del task_id
    if not query.strip():
        return tool_error("Query is required.")

    backend_used = None
    last_error = None
    for backend in _search_backends():
        if not backend.is_available():
            continue
        backend_used = backend.name
        try:
            results = backend.search(query, max_results, domains, freshness_days)
            return tool_result(
                {
                    "query": query,
                    "results": results,
                    "total": len(results),
                    "backend": backend.name,
                }
            )
        except Exception as exc:
            last_error = str(exc)

    return tool_error(
        "Search request failed.",
        backend=backend_used,
        details=last_error or "No search backend available.",
    )


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "nav", "footer"}:
            self._skip_depth += 1
        elif tag in {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "h5", "h6"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "nav", "footer"} and self._skip_depth:
            self._skip_depth -= 1
        elif tag in {"p", "div", "br", "li"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip_depth:
            self.parts.append(data)


def _web_extract(url: str, max_chars: int = 12000, task_id: str | None = None) -> str:
    del task_id
    import httpx

    headers = {
        "User-Agent": _USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    try:
        with httpx.Client(timeout=20.0, follow_redirects=True) as client:
            resp = client.get(url, headers=headers)
            resp.raise_for_status()
            raw_html = resp.text
            final_url = str(resp.url)
    except Exception as exc:
        return tool_error(f"Failed to fetch URL: {exc}")

    content = _extract_readable_text(raw_html)
    truncated = len(content) > max_chars
    if truncated:
        content = content[:max_chars]

    metadata = _extract_metadata(raw_html, final_url)
    return tool_result(
        {
            "url": url,
            "title": metadata.get("title", ""),
            "canonical_url": metadata.get("canonical_url", final_url),
            "published_at": metadata.get("published_at"),
            "content": content,
            "truncated": truncated,
        }
    )


def _extract_readable_text(raw_html: str) -> str:
    try:
        from readability import Document

        summary_html = Document(raw_html).summary()
        return _html_to_text(summary_html)
    except Exception:
        return _html_to_text(raw_html)


def _html_to_text(raw_html: str) -> str:
    parser = _TextExtractor()
    parser.feed(raw_html)
    text = html.unescape("".join(parser.parts))
    lines = [line.strip() for line in text.splitlines()]
    normalized = "\n".join(line for line in lines if line)
    return re.sub(r"\n{3,}", "\n\n", normalized).strip()


def _extract_metadata(raw_html: str, fallback_url: str) -> dict[str, Any]:
    title_match = re.search(r"<title[^>]*>(.*?)</title>", raw_html, re.IGNORECASE | re.DOTALL)
    title = _strip_tags(title_match.group(1)).strip() if title_match else ""

    canonical_match = re.search(
        r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\']([^"\']+)["\']',
        raw_html,
        re.IGNORECASE,
    )
    canonical_url = canonical_match.group(1).strip() if canonical_match else fallback_url

    published_match = re.search(
        r'<meta[^>]+(?:property|name)=["\'](?:article:published_time|og:published_time|pubdate|datePublished)["\'][^>]+content=["\']([^"\']+)["\']',
        raw_html,
        re.IGNORECASE,
    )

    return {
        "title": title,
        "canonical_url": canonical_url,
        "published_at": published_match.group(1).strip() if published_match else None,
    }


def _filter_and_rank_results(
    results: list[dict[str, Any]],
    backend: str,
    domains: list[str] | None,
    max_results: int,
) -> list[dict[str, Any]]:
    filtered: list[dict[str, Any]] = []
    for item in results:
        url = item.get("url", "")
        if domains and not _matches_domains(url, domains):
            continue
        filtered.append(item)
        if len(filtered) >= max_results:
            break

    normalized: list[dict[str, Any]] = []
    for idx, item in enumerate(filtered, start=1):
        normalized.append(
            {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "snippet": item.get("snippet", ""),
                "rank": idx,
                "backend": backend,
            }
        )
    return normalized


def _matches_domains(url: str, domains: list[str]) -> bool:
    host = urlparse(url).netloc.lower()
    return any(
        host == domain.lower() or host.endswith(f".{domain.lower()}")
        for domain in domains
    )


def _add_domain_filters(query: str, domains: list[str] | None) -> str:
    if not domains:
        return query
    domain_terms = " OR ".join(f"site:{domain}" for domain in domains)
    return f"{query} ({domain_terms})"


def _unwrap_duckduckgo_url(href: str) -> str:
    if "uddg=" not in href:
        return href
    parsed = urlparse(href)
    query = parse_qs(parsed.query)
    return unquote(query.get("uddg", [href])[0])


def _strip_tags(value: str) -> str:
    return re.sub(r"<[^>]+>", "", value).strip()


registry.register(
    name="web_search",
    toolset="web",
    schema={
        "name": "web_search",
        "description": (
            "Search the web for current information and sources. Returns normalized "
            "results with title, URL, snippet, rank, and backend."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "max_results": {"type": "integer", "default": 5},
                "domains": {"type": "array", "items": {"type": "string"}},
                "freshness_days": {"type": "integer"},
            },
            "required": ["query"],
        },
    },
    handler=lambda args, **kw: _web_search(
        query=args.get("query", ""),
        max_results=int(args.get("max_results", 5)),
        domains=args.get("domains"),
        freshness_days=args.get("freshness_days"),
        task_id=kw.get("task_id"),
    ),
)

registry.register(
    name="web_extract",
    toolset="web",
    schema={
        "name": "web_extract",
        "description": (
            "Fetch and extract readable page content with title, canonical URL, and "
            "published date metadata when available."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "max_chars": {"type": "integer", "default": 12000},
            },
            "required": ["url"],
        },
    },
    handler=lambda args, **kw: _web_extract(
        url=args.get("url", ""),
        max_chars=int(args.get("max_chars", 12000)),
        task_id=kw.get("task_id"),
    ),
)
