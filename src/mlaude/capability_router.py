"""Heuristic capability router for browser-first tool exposure."""

from __future__ import annotations

from dataclasses import dataclass


_BROWSER_KEYWORDS = {
    "open",
    "click",
    "fill",
    "login",
    "scroll",
    "page",
    "site",
    "browser",
    "navigate",
    "visit",
    "tab",
    "form",
}

_FRESH_WEB_KEYWORDS = {
    "latest",
    "current",
    "today",
    "news",
    "docs",
    "documentation",
    "version",
    "release",
    "source",
    "link",
}

_DELEGATION_KEYWORDS = {
    "research",
    "summarize",
    "summary",
    "compare",
    "comparison",
    "evaluate",
    "review options",
}


@dataclass(frozen=True)
class CapabilityRoute:
    name: str
    tool_names: tuple[str, ...]
    system_prompt_suffix: str = ""


ROUTES: dict[str, CapabilityRoute] = {
    "browser_task": CapabilityRoute(
        name="browser_task",
        tool_names=(
            "browser_navigate",
            "browser_snapshot",
            "browser_click",
            "browser_type",
            "browser_scroll",
            "web_extract",
        ),
        system_prompt_suffix=(
            "This turn is a browser automation task. Prefer browser tools and use snapshot "
            "element IDs for interactions."
        ),
    ),
    "fresh_web": CapabilityRoute(
        name="fresh_web",
        tool_names=("web_search", "web_extract"),
        system_prompt_suffix=(
            "This turn requires fresh web information. Use web_search at least once before "
            "answering, verify claims against fetched sources, and include URL citations in "
            "the final answer."
        ),
    ),
    "delegation_candidate": CapabilityRoute(
        name="delegation_candidate",
        tool_names=("delegate_task",),
        system_prompt_suffix=(
            "This turn may be delegated only if the subtask is contained research, "
            "summarization, or comparison work. Do not delegate live browser execution."
        ),
    ),
    "local_code": CapabilityRoute(
        name="local_code",
        tool_names=(),
    ),
}


def classify_capability_route(user_message: str) -> CapabilityRoute:
    text = user_message.lower()

    if _contains_any(text, _BROWSER_KEYWORDS):
        return ROUTES["browser_task"]
    if _contains_any(text, _FRESH_WEB_KEYWORDS):
        return ROUTES["fresh_web"]
    if _contains_any(text, _DELEGATION_KEYWORDS):
        return ROUTES["delegation_candidate"]
    return ROUTES["local_code"]


def filter_tools_for_route(route: CapabilityRoute, platform_tools: list[str]) -> list[str]:
    if route.name == "local_code":
        return list(platform_tools)
    allowed = set(route.tool_names)
    return [tool_name for tool_name in platform_tools if tool_name in allowed]


def _contains_any(text: str, keywords: set[str]) -> bool:
    return any(keyword in text for keyword in keywords)
