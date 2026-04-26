"""Web tools — search and content extraction.

Registered via the tool registry for auto-discovery.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any
from urllib.parse import quote_plus

from mlaude.tools.registry import registry, tool_error, tool_result

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# web_search — DuckDuckGo HTML scraping (no API key needed)
# ---------------------------------------------------------------------------


def _web_search(query: str, max_results: int = 5, task_id: str = None) -> str:
    """Search the web via DuckDuckGo HTML."""
    import httpx

    url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
    }

    try:
        with httpx.Client(timeout=15.0, follow_redirects=True) as client:
            resp = client.get(url, headers=headers)
            resp.raise_for_status()
            html = resp.text
    except Exception as e:
        return tool_error(f"Search request failed: {e}")

    # Parse results from DuckDuckGo HTML
    results: list[dict] = []

    # Extract result blocks
    result_pattern = re.compile(
        r'<a[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>.*?'
        r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>',
        re.DOTALL,
    )

    for match in result_pattern.finditer(html):
        if len(results) >= max_results:
            break
        href = match.group(1)
        title = re.sub(r"<[^>]+>", "", match.group(2)).strip()
        snippet = re.sub(r"<[^>]+>", "", match.group(3)).strip()

        # DuckDuckGo wraps URLs in a redirect
        if "uddg=" in href:
            from urllib.parse import unquote, parse_qs, urlparse
            parsed = urlparse(href)
            qs = parse_qs(parsed.query)
            href = unquote(qs.get("uddg", [href])[0])

        results.append({
            "title": title,
            "url": href,
            "snippet": snippet,
        })

    if not results:
        # Fallback: simpler pattern
        link_pattern = re.compile(
            r'<a[^>]*class="result__url"[^>]*href="([^"]*)"[^>]*>(.*?)</a>',
            re.DOTALL,
        )
        for match in link_pattern.finditer(html):
            if len(results) >= max_results:
                break
            results.append({
                "title": re.sub(r"<[^>]+>", "", match.group(2)).strip(),
                "url": match.group(1),
                "snippet": "",
            })

    return tool_result({
        "query": query,
        "results": results,
        "total": len(results),
    })


registry.register(
    name="web_search",
    toolset="web",
    schema={
        "name": "web_search",
        "description": (
            "Search the web for information. Returns titles, URLs, and snippets "
            "from search results. Use this when you need current information or "
            "to find specific web resources."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query.",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of results (default 5).",
                    "default": 5,
                },
            },
            "required": ["query"],
        },
    },
    handler=lambda args, **kw: _web_search(
        query=args.get("query", ""),
        max_results=args.get("max_results", 5),
        task_id=kw.get("task_id"),
    ),
)


# ---------------------------------------------------------------------------
# web_extract — page content extraction
# ---------------------------------------------------------------------------


def _web_extract(url: str, max_chars: int = 12000, task_id: str = None) -> str:
    """Extract text content from a URL."""
    import httpx

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    try:
        with httpx.Client(timeout=20.0, follow_redirects=True) as client:
            resp = client.get(url, headers=headers)
            resp.raise_for_status()
            html = resp.text
    except Exception as e:
        return tool_error(f"Failed to fetch URL: {e}")

    # Extract readable text from HTML
    text = _html_to_text(html)

    truncated = False
    if len(text) > max_chars:
        text = text[:max_chars]
        truncated = True

    return tool_result({
        "url": url,
        "content": text,
        "length": len(text),
        "truncated": truncated,
    })


def _html_to_text(html: str) -> str:
    """Convert HTML to readable plain text."""
    # Remove script/style tags
    text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL)
    text = re.sub(r"<nav[^>]*>.*?</nav>", "", text, flags=re.DOTALL)
    text = re.sub(r"<footer[^>]*>.*?</footer>", "", text, flags=re.DOTALL)

    # Convert common elements
    text = re.sub(r"<br\s*/?>", "\n", text)
    text = re.sub(r"</?p[^>]*>", "\n", text)
    text = re.sub(r"</?div[^>]*>", "\n", text)
    text = re.sub(r"</?li[^>]*>", "\n• ", text)
    text = re.sub(r"<h[1-6][^>]*>(.*?)</h[1-6]>", r"\n## \1\n", text, flags=re.DOTALL)

    # Remove remaining tags
    text = re.sub(r"<[^>]+>", "", text)

    # Decode HTML entities
    import html as html_lib
    text = html_lib.unescape(text)

    # Normalize whitespace
    lines = [line.strip() for line in text.splitlines()]
    text = "\n".join(line for line in lines if line)

    # Collapse multiple blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


registry.register(
    name="web_extract",
    toolset="web",
    schema={
        "name": "web_extract",
        "description": (
            "Extract the text content of a web page. Strips HTML tags and "
            "returns readable text. Use this to read articles, documentation, "
            "and other web content."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The URL to extract content from.",
                },
                "max_chars": {
                    "type": "integer",
                    "description": "Maximum characters to return (default 12000).",
                    "default": 12000,
                },
            },
            "required": ["url"],
        },
    },
    handler=lambda args, **kw: _web_extract(
        url=args.get("url", ""),
        max_chars=args.get("max_chars", 12000),
        task_id=kw.get("task_id"),
    ),
)
