from __future__ import annotations

import asyncio
import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import httpx
from duckduckgo_search import DDGS

try:  # pragma: no cover - optional runtime dependency
    import trafilatura
except Exception:  # pragma: no cover - optional runtime dependency
    trafilatura = None

try:  # pragma: no cover - optional runtime dependency
    from readability import Document
except Exception:  # pragma: no cover - optional runtime dependency
    Document = None


TRACKING_QUERY_KEYS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "ref",
    "ref_src",
    "fbclid",
    "gclid",
}


def strip_html(value: str) -> str:
    value = re.sub(r"<script.*?</script>", " ", value, flags=re.DOTALL | re.IGNORECASE)
    value = re.sub(r"<style.*?</style>", " ", value, flags=re.DOTALL | re.IGNORECASE)
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def canonicalize_url(url: str) -> str:
    parsed = urlparse(url.strip())
    scheme = parsed.scheme or "https"
    netloc = parsed.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]

    query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in TRACKING_QUERY_KEYS
    ]
    query.sort()

    path = parsed.path or "/"
    if path != "/" and path.endswith("/"):
        path = path[:-1]

    return urlunparse((scheme, netloc, path, "", urlencode(query), ""))


async def search_web(query: str, max_results: int = 5) -> list[dict[str, Any]]:
    def _run_search() -> list[dict[str, Any]]:
        with DDGS() as ddgs:
            return list(ddgs.text(query, max_results=max_results))

    raw_results = await asyncio.to_thread(_run_search)

    normalized: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    fetched_at = datetime.now(UTC).isoformat()
    for rank, item in enumerate(raw_results, start=1):
        raw_url = item.get("href") or item.get("url") or ""
        if not raw_url:
            continue
        canonical_url = canonicalize_url(raw_url)
        if canonical_url in seen_urls:
            continue
        seen_urls.add(canonical_url)
        snippet = (item.get("body") or item.get("snippet") or "").strip()
        title = (item.get("title") or urlparse(canonical_url).netloc or canonical_url).strip()
        normalized.append(
            {
                "document_id": f"web-result:{rank}:{canonical_url}",
                "file_id": None,
                "title": title,
                "source": canonical_url,
                "source_kind": "web_result",
                "section": "Search Result",
                "content": snippet[:1200],
                "preview": snippet[:280],
                "query": query,
                "rank": rank,
                "score": round(max(0.0, 1.0 - (rank - 1) * 0.08), 3),
                "retrieval_score": round(max(0.0, 1.0 - (rank - 1) * 0.08), 3),
                "fetched_at": fetched_at,
                "extract_status": "not_fetched",
                "canonical_url": canonical_url,
            }
        )

    return normalized


async def fetch_pages(urls: list[str], timeout: float = 12.0) -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        tasks = [client.get(url, headers={"User-Agent": "mlaude/0.2"}) for url in urls]
        responses = await asyncio.gather(*tasks, return_exceptions=True)

    pages: list[dict[str, Any]] = []
    for url, response in zip(urls, responses, strict=False):
        canonical_url = canonicalize_url(url)
        fetched_at = datetime.now(UTC).isoformat()
        if isinstance(response, Exception):
            pages.append(
                {
                    "canonical_url": canonical_url,
                    "url": url,
                    "status_code": None,
                    "html": "",
                    "fetched_at": fetched_at,
                    "error": str(response),
                }
            )
            continue
        pages.append(
            {
                "canonical_url": canonicalize_url(str(response.url)),
                "url": str(response.url),
                "status_code": response.status_code,
                "html": response.text,
                "fetched_at": fetched_at,
                "error": None,
            }
        )
    return pages


def extract_page_content(html: str, url: str) -> dict[str, str]:
    title = urlparse(url).netloc or url
    content = ""
    extract_status = "failed"

    if trafilatura is not None:
        try:
            content = (
                trafilatura.extract(
                    html,
                    url=url,
                    include_links=False,
                    include_tables=True,
                    favor_precision=True,
                )
                or ""
            ).strip()
            if content:
                extract_status = "complete"
        except Exception:
            content = ""

    if not content and Document is not None:
        try:
            readable = Document(html)
            title = readable.title() or title
            content = strip_html(readable.summary())
            if content:
                extract_status = "readability_fallback"
        except Exception:
            content = ""

    if not content:
        content = strip_html(html)
        if content:
            extract_status = "html_fallback"

    return {
        "title": title.strip(),
        "content": content.strip(),
        "preview": content[:280].strip(),
        "extract_status": extract_status,
    }


def page_to_document(
    *,
    page: dict[str, Any],
    query: str,
    rank: int,
) -> dict[str, Any]:
    extracted = extract_page_content(page.get("html", ""), page["canonical_url"])
    return {
        "document_id": f"web-page:{rank}:{page['canonical_url']}",
        "file_id": None,
        "title": extracted["title"] or page["canonical_url"],
        "source": page["canonical_url"],
        "source_kind": "web_page",
        "section": "Fetched Page",
        "content": extracted["content"][:4000],
        "preview": extracted["preview"],
        "query": query,
        "rank": rank,
        "score": round(max(0.0, 1.1 - (rank - 1) * 0.08), 3),
        "retrieval_score": round(max(0.0, 1.1 - (rank - 1) * 0.08), 3),
        "fetched_at": page.get("fetched_at"),
        "extract_status": extracted["extract_status"],
        "canonical_url": page["canonical_url"],
        "status_code": page.get("status_code"),
        "fetch_error": page.get("error"),
    }
