"""Web search tool — Tavily (if API key) with DuckDuckGo fallback."""

import asyncio
import logging

from mlaude.config import TAVILY_API_KEY
from mlaude.tools_base import Tool, ToolResult

logger = logging.getLogger("mlaude")


class WebSearchTool(Tool):
    name = "web_search"
    description = (
        "Search the web for current information, news, prices, live data, "
        "or facts you are uncertain about. Do NOT use for things you already know."
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query",
            },
        },
        "required": ["query"],
    }

    async def run(self, *, query: str) -> ToolResult:
        results = await self._tavily(query) if TAVILY_API_KEY else await self._ddg(query)
        if not results:
            return ToolResult(output="No results found.", error=True)
        formatted = "\n\n".join(
            f"**{r['title']}**\n{r['snippet']}\nSource: {r['url']}"
            for r in results[:5]
        )
        return ToolResult(output=formatted)

    async def _tavily(self, query: str) -> list[dict]:
        try:
            from tavily import AsyncTavilyClient

            client = AsyncTavilyClient(api_key=TAVILY_API_KEY)
            resp = await client.search(query, max_results=5)
            return [
                {"title": r.get("title", ""), "snippet": r.get("content", ""), "url": r.get("url", "")}
                for r in resp.get("results", [])
            ]
        except Exception as e:
            logger.warning("Tavily search failed, falling back to DDG: %s", e)
            return await self._ddg(query)

    async def _ddg(self, query: str) -> list[dict]:
        try:
            from duckduckgo_search import DDGS

            loop = asyncio.get_event_loop()
            results = await loop.run_in_executor(
                None, lambda: list(DDGS().text(query, max_results=5))
            )
            return [
                {"title": r.get("title", ""), "snippet": r.get("body", ""), "url": r.get("href", "")}
                for r in results
            ]
        except Exception as e:
            logger.error("DuckDuckGo search failed: %s", e)
            return []
