"""Playwright-backed browser automation tools."""

from __future__ import annotations

import importlib.util
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from mlaude.tools.registry import registry, tool_error, tool_result


def _has_playwright() -> bool:
    return importlib.util.find_spec("playwright.sync_api") is not None


def _validate_url(url: str) -> str | None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return "Only http:// and https:// URLs are allowed."
    return None


@dataclass
class BrowserSessionState:
    playwright: Any
    browser: Any
    context: Any
    page: Any
    last_elements: dict[str, Any] = field(default_factory=dict)


class BrowserSessionManager:
    """Keeps a persistent browser context per agent session."""

    def __init__(self) -> None:
        self._sessions: dict[str, BrowserSessionState] = {}

    def get_state(self, session_id: str) -> BrowserSessionState:
        from playwright.sync_api import sync_playwright

        state = self._sessions.get(session_id)
        if state:
            return state

        playwright = sync_playwright().start()
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(accept_downloads=False)
        page = context.new_page()
        state = BrowserSessionState(
            playwright=playwright,
            browser=browser,
            context=context,
            page=page,
        )
        self._sessions[session_id] = state
        return state


_BROWSER_MANAGER = BrowserSessionManager()


def _browser_navigate(url: str, new_tab: bool = False, task_id: str | None = None) -> str:
    error = _validate_url(url)
    if error:
        return tool_error(error)
    if not task_id:
        return tool_error("session_id is required for browser sessions.")

    state = _BROWSER_MANAGER.get_state(task_id)
    page = state.context.new_page() if new_tab else state.page
    state.page = page
    page.goto(url, wait_until="domcontentloaded")
    return tool_result({
        "url": page.url,
        "title": page.title(),
        "new_tab": new_tab,
    })


def _browser_snapshot(
    include_screenshot: bool = False,
    max_elements: int = 80,
    task_id: str | None = None,
) -> str:
    if not task_id:
        return tool_error("session_id is required for browser sessions.")

    state = _BROWSER_MANAGER.get_state(task_id)
    page = state.page

    handles = page.query_selector_all(
        "a, button, input, textarea, select, summary, [role], [tabindex]"
    )
    elements: list[dict[str, Any]] = []
    element_map: dict[str, Any] = {}

    for handle in handles:
        if len(elements) >= max_elements:
            break
        try:
            visible = bool(handle.is_visible())
            enabled = bool(handle.is_enabled())
            text = (handle.inner_text(timeout=250) or "").strip()
            name = (
                handle.get_attribute("aria-label")
                or handle.get_attribute("name")
                or handle.get_attribute("title")
                or text
            )
            role = (
                handle.get_attribute("role")
                or handle.evaluate("(el) => el.tagName.toLowerCase()")
            )
        except Exception:
            continue

        element_id = f"e{len(elements) + 1}"
        element_map[element_id] = handle
        elements.append({
            "element_id": element_id,
            "role": role or "",
            "name": (name or "").strip(),
            "text": text,
            "enabled": enabled,
            "visible": visible,
        })

    state.last_elements = element_map

    screenshot_path = None
    if include_screenshot:
        screenshot_path = str(
            Path(tempfile.gettempdir()) / f"mlaude-browser-{task_id[:8]}-{int(time.time())}.png"
        )
        page.screenshot(path=screenshot_path, full_page=True)

    body_text = page.locator("body").inner_text(timeout=1000) if page.url else ""
    excerpt = body_text[:4000]

    return tool_result({
        "url": page.url,
        "title": page.title() if page.url else "",
        "screenshot_path": screenshot_path,
        "visible_text_excerpt": excerpt,
        "elements": elements,
    })


def _lookup_element(task_id: str, element_id: str) -> tuple[Any | None, str | None]:
    state = _BROWSER_MANAGER.get_state(task_id)
    handle = state.last_elements.get(element_id)
    if handle is None:
        return None, "Unknown element_id. Call browser_snapshot first and use its element IDs."
    return handle, None


def _browser_click(element_id: str, button: str = "left", task_id: str | None = None) -> str:
    if not task_id:
        return tool_error("session_id is required for browser sessions.")
    handle, error = _lookup_element(task_id, element_id)
    if error:
        return tool_error(error)
    handle.click(button=button)
    return tool_result({"clicked": element_id, "button": button})


def _browser_type(
    element_id: str,
    text: str,
    submit: bool = False,
    task_id: str | None = None,
) -> str:
    if not task_id:
        return tool_error("session_id is required for browser sessions.")
    handle, error = _lookup_element(task_id, element_id)
    if error:
        return tool_error(error)
    input_type = (handle.get_attribute("type") or "").lower()
    if input_type == "file":
        return tool_error("Uploads are disabled in browser v1.")
    handle.fill(text)
    if submit:
        handle.press("Enter")
    return tool_result({"typed_into": element_id, "submitted": submit})


def _browser_scroll(direction: str = "down", amount: int = 1200, task_id: str | None = None) -> str:
    if not task_id:
        return tool_error("session_id is required for browser sessions.")
    state = _BROWSER_MANAGER.get_state(task_id)
    delta = amount if direction.lower() == "down" else -amount
    state.page.mouse.wheel(0, delta)
    return tool_result({"direction": direction, "amount": amount})


_COMMON_CHECK = _has_playwright

registry.register(
    name="browser_navigate",
    toolset="browser",
    schema={
        "name": "browser_navigate",
        "description": "Navigate the persistent browser session to an http/https URL.",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "new_tab": {"type": "boolean", "default": False},
            },
            "required": ["url"],
        },
    },
    handler=lambda args, **kw: _browser_navigate(
        url=args.get("url", ""),
        new_tab=bool(args.get("new_tab", False)),
        task_id=kw.get("task_id"),
    ),
    check_fn=_COMMON_CHECK,
)

registry.register(
    name="browser_snapshot",
    toolset="browser",
    schema={
        "name": "browser_snapshot",
        "description": (
            "Capture a page summary and interactive element map for the browser session."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "include_screenshot": {"type": "boolean", "default": False},
                "max_elements": {"type": "integer", "default": 80},
            },
        },
    },
    handler=lambda args, **kw: _browser_snapshot(
        include_screenshot=bool(args.get("include_screenshot", False)),
        max_elements=int(args.get("max_elements", 80)),
        task_id=kw.get("task_id"),
    ),
    check_fn=_COMMON_CHECK,
)

registry.register(
    name="browser_click",
    toolset="browser",
    schema={
        "name": "browser_click",
        "description": "Click an element from the latest browser_snapshot by element_id.",
        "parameters": {
            "type": "object",
            "properties": {
                "element_id": {"type": "string"},
                "button": {"type": "string", "default": "left"},
            },
            "required": ["element_id"],
        },
    },
    handler=lambda args, **kw: _browser_click(
        element_id=args.get("element_id", ""),
        button=args.get("button", "left"),
        task_id=kw.get("task_id"),
    ),
    check_fn=_COMMON_CHECK,
)

registry.register(
    name="browser_type",
    toolset="browser",
    schema={
        "name": "browser_type",
        "description": "Type into an element from the latest browser_snapshot by element_id.",
        "parameters": {
            "type": "object",
            "properties": {
                "element_id": {"type": "string"},
                "text": {"type": "string"},
                "submit": {"type": "boolean", "default": False},
            },
            "required": ["element_id", "text"],
        },
    },
    handler=lambda args, **kw: _browser_type(
        element_id=args.get("element_id", ""),
        text=args.get("text", ""),
        submit=bool(args.get("submit", False)),
        task_id=kw.get("task_id"),
    ),
    check_fn=_COMMON_CHECK,
)

registry.register(
    name="browser_scroll",
    toolset="browser",
    schema={
        "name": "browser_scroll",
        "description": "Scroll the active browser page up or down.",
        "parameters": {
            "type": "object",
            "properties": {
                "direction": {"type": "string", "default": "down"},
                "amount": {"type": "integer", "default": 1200},
            },
        },
    },
    handler=lambda args, **kw: _browser_scroll(
        direction=args.get("direction", "down"),
        amount=int(args.get("amount", 1200)),
        task_id=kw.get("task_id"),
    ),
    check_fn=_COMMON_CHECK,
)
