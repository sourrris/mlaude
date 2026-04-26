from __future__ import annotations

import asyncio
import hashlib
import json
import re
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

from mlaude.runtime import BaseRuntime
from mlaude.settings import (
    PLAYWRIGHT_BROWSER,
    PLAYWRIGHT_ENABLED,
    PLAYWRIGHT_HEADLESS,
    PLAYWRIGHT_MAX_STEPS,
    PLAYWRIGHT_OUTPUT_DIR,
    PLAYWRIGHT_PROFILE_DIR,
    PLAYWRIGHT_SEARCH_ENGINE,
    PLAYWRIGHT_TOOL_TIMEOUT_SECONDS,
    ensure_app_dirs,
)


MAX_MODEL_VISIBLE_CHARS = 9000
MAX_DOCUMENT_CHARS = 5200
MAX_RESULT_COUNT = 5
URL_RE = re.compile(r"https?://[^\s<>()\"']+", re.IGNORECASE)
SECRET_RE = re.compile(
    r"(?i)(cookie|authorization|bearer|token|secret|password|passwd|api[_-]?key)"
    r"\s*[:=]\s*(?:bearer\s+)?[^\s,;]+"
)
SENSITIVE_RE = re.compile(
    r"(?i)\b(password|passcode|2fa|otp|verification code|credit card|card number|cvv|"
    r"payment|purchase|buy now|place order|transfer|wire|send money|delete account|"
    r"close account|irreversible|submit payment)\b"
)
DESTRUCTIVE_TOOL_RE = re.compile(r"(?i)(click|type|press|select|drag|upload|file)")


class BrowserMCPError(RuntimeError):
    pass


class BrowserGuardrailError(BrowserMCPError):
    pass


@dataclass
class BrowserSearchResult:
    documents: list[dict[str, Any]]
    packets: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class BrowserControlResult:
    documents: list[dict[str, Any]]
    packets: list[dict[str, Any]] = field(default_factory=list)
    final_response: str | None = None


def utc_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def truncate_text(value: str, limit: int = MAX_MODEL_VISIBLE_CHARS) -> str:
    collapsed = re.sub(r"\n{3,}", "\n\n", value.strip())
    return collapsed[:limit]


def redact_secrets(value: str) -> str:
    return SECRET_RE.sub(lambda match: f"{match.group(1)}=[REDACTED]", value)


def sanitize_text(value: str, limit: int = MAX_MODEL_VISIBLE_CHARS) -> str:
    return truncate_text(redact_secrets(value), limit)


def canonicalize_result_url(url: str) -> str:
    value = url.strip()
    parsed = urlparse(value)
    if parsed.netloc.endswith("google.com") and parsed.path == "/url":
        nested = parse_qs(parsed.query).get("q", [""])[0]
        if nested:
            value = nested
    return unquote(value).rstrip(".,)")


def extract_urls(value: str) -> list[str]:
    return [canonicalize_result_url(match.group(0)) for match in URL_RE.finditer(value)]


def is_consent_or_captcha(snapshot: str) -> bool:
    lowered = snapshot.lower()
    return any(
        marker in lowered
        for marker in (
            "unusual traffic",
            "our systems have detected",
            "captcha",
            "before you continue to google",
            "consent.google.com",
        )
    )


def guardrail_violation(user_request: str, tool_name: str, arguments: dict[str, Any]) -> str | None:
    combined = f"{user_request}\n{tool_name}\n{json.dumps(arguments, default=str)}"
    if SENSITIVE_RE.search(combined) and DESTRUCTIVE_TOOL_RE.search(tool_name):
        return "Sensitive browser action needs explicit user confirmation."

    typed_value = str(
        arguments.get("text")
        or arguments.get("value")
        or arguments.get("inputValue")
        or ""
    ).strip()
    if typed_value and typed_value not in user_request:
        return "Browser typing is limited to values explicitly present in the request."
    return None


def mcp_result_to_text(result: Any) -> str:
    pieces: list[str] = []
    structured = getattr(result, "structuredContent", None) or getattr(
        result, "structured_content", None
    )
    if structured:
        pieces.append(json.dumps(structured, default=str))

    for item in getattr(result, "content", []) or []:
        text = getattr(item, "text", None)
        if text:
            pieces.append(str(text))
        data = getattr(item, "data", None)
        if data and not text:
            pieces.append(str(data)[:300])

    if not pieces:
        pieces.append(str(result))
    return sanitize_text("\n".join(pieces))


def page_document(
    *,
    url: str,
    title: str,
    text: str,
    query: str,
    index: int,
    source_kind: str = "web_page",
) -> dict[str, Any]:
    cleaned = sanitize_text(text, MAX_DOCUMENT_CHARS)
    source = canonicalize_result_url(url)
    digest = hashlib.sha1(f"{source}|{title}|{index}".encode("utf-8")).hexdigest()[:12]
    doc_id = f"browser:{digest}:{index}"
    return {
        "document_id": doc_id,
        "file_id": None,
        "title": title.strip() or source,
        "source": source,
        "source_kind": source_kind,
        "section": "Browser",
        "content": cleaned,
        "preview": cleaned[:280],
        "query": query,
        "score": 1.0,
        "retrieval_score": 1.0,
        "fetched_at": utc_iso(),
        "extract_status": "complete" if cleaned else "empty",
    }


class BrowserMCPService:
    def __init__(self) -> None:
        ensure_app_dirs()
        self.enabled = PLAYWRIGHT_ENABLED
        self.max_steps = PLAYWRIGHT_MAX_STEPS
        self.timeout_seconds = PLAYWRIGHT_TOOL_TIMEOUT_SECONDS
        self.search_engine = PLAYWRIGHT_SEARCH_ENGINE.lower()
        self._lock = asyncio.Lock()
        self._exit_stack: AsyncExitStack | None = None
        self._session: Any | None = None
        self._tools: set[str] = set()

    async def close(self) -> None:
        if self._exit_stack is not None:
            await self._exit_stack.aclose()
        self._exit_stack = None
        self._session = None
        self._tools = set()

    async def _ensure_session(self) -> None:
        if not self.enabled:
            raise BrowserMCPError("Playwright browser tools are disabled.")
        if self._session is not None:
            return

        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
        except Exception as exc:  # pragma: no cover - depends on optional runtime install
            raise BrowserMCPError(
                "Python package 'mcp' is required for Playwright browser tools."
            ) from exc

        args = [
            "-y",
            "@playwright/mcp@latest",
            f"--browser={PLAYWRIGHT_BROWSER}",
            f"--user-data-dir={PLAYWRIGHT_PROFILE_DIR}",
            f"--output-dir={PLAYWRIGHT_OUTPUT_DIR}",
            "--viewport-size=1440x1000",
            "--caps=network,storage,testing,vision,pdf,devtools,config",
        ]
        if PLAYWRIGHT_HEADLESS:
            args.append("--headless")

        stack = AsyncExitStack()
        try:
            server_params = StdioServerParameters(command="npx", args=args)
            read, write = await stack.enter_async_context(stdio_client(server_params))
            session = await stack.enter_async_context(ClientSession(read, write))
            await asyncio.wait_for(session.initialize(), timeout=self.timeout_seconds)
            tools_result = await asyncio.wait_for(
                session.list_tools(),
                timeout=self.timeout_seconds,
            )
            self._tools = {tool.name for tool in getattr(tools_result, "tools", [])}
            self._session = session
            self._exit_stack = stack
        except Exception:
            await stack.aclose()
            raise

    def _require_tool(self, name: str) -> str:
        aliases = {
            "snapshot": "browser_snapshot",
            "navigate": "browser_navigate",
            "evaluate": "browser_evaluate",
            "click": "browser_click",
            "type": "browser_type",
            "press": "browser_press_key",
            "select": "browser_select_option",
            "screenshot": "browser_take_screenshot",
            "pdf": "browser_pdf_save",
            "console": "browser_console_messages",
            "network": "browser_network_requests",
        }
        candidate = aliases.get(name, name)
        if candidate not in self._tools:
            raise BrowserMCPError(f"Playwright MCP tool is unavailable: {candidate}")
        return candidate

    async def _call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> str:
        await self._ensure_session()
        assert self._session is not None
        tool_name = self._require_tool(name)
        result = await asyncio.wait_for(
            self._session.call_tool(tool_name, arguments or {}),
            timeout=self.timeout_seconds,
        )
        return mcp_result_to_text(result)

    async def _snapshot_packet(self) -> dict[str, Any]:
        snapshot = await self._call_tool("browser_snapshot", {})
        title, url = parse_snapshot_title_url(snapshot)
        return {
            "type": "browser_snapshot",
            "title": title,
            "url": url,
            "text": sanitize_text(snapshot, 1800),
        }

    async def _evaluate_json(self, function: str) -> Any:
        raw = await self._call_tool("browser_evaluate", {"function": function})
        match = re.search(r"(\{.*\}|\[.*\])", raw, re.DOTALL)
        if not match:
            return raw
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            return raw

    async def search(self, query: str, *, max_results: int = MAX_RESULT_COUNT) -> BrowserSearchResult:
        if self.search_engine != "google":
            raise BrowserMCPError("Only Google-in-browser search is currently configured.")

        async with self._lock:
            packets: list[dict[str, Any]] = []
            search_url = f"https://www.google.com/search?q={quote_plus(query)}"
            packets.append(
                {
                    "type": "browser_tool_start",
                    "tool": "browser_navigate",
                    "summary": f"Opening Google search for {query}",
                    "arguments": {"url": search_url},
                }
            )
            nav_result = await self._call_tool("browser_navigate", {"url": search_url})
            packets.append(
                {
                    "type": "browser_tool_result",
                    "tool": "browser_navigate",
                    "status": "completed",
                    "summary": sanitize_text(nav_result, 600),
                }
            )

            snapshot_packet = await self._snapshot_packet()
            packets.append(snapshot_packet)
            if is_consent_or_captcha(snapshot_packet.get("text", "")):
                raise BrowserMCPError(
                    "Google needs consent or CAPTCHA handling in the visible browser."
                )

            result_rows = await self._evaluate_json(
                """() => Array.from(document.querySelectorAll('a')).map((anchor) => {
                  const container = anchor.closest('div');
                  const title = anchor.querySelector('h3')?.innerText || anchor.innerText || '';
                  const href = anchor.href || '';
                  const snippet = container?.innerText || '';
                  return { title, url: href, snippet };
                }).filter((item) => item.title && item.url).slice(0, 12)"""
            )

            rows = normalize_google_results(result_rows)[:max_results]
            documents: list[dict[str, Any]] = []
            for index, row in enumerate(rows, start=1):
                url = row["url"]
                packets.append(
                    {
                        "type": "browser_tool_start",
                        "tool": "browser_navigate",
                        "summary": f"Opening result {index}: {row['title']}",
                        "arguments": {"url": url},
                    }
                )
                await self._call_tool("browser_navigate", {"url": url})
                page_payload = await self._evaluate_json(
                    """() => ({
                      title: document.title,
                      url: location.href,
                      text: document.body ? document.body.innerText : ''
                    })"""
                )
                if not isinstance(page_payload, dict):
                    page_payload = {"title": row["title"], "url": url, "text": row.get("snippet", "")}
                title = str(page_payload.get("title") or row["title"])
                final_url = str(page_payload.get("url") or url)
                text = str(page_payload.get("text") or row.get("snippet", ""))
                documents.append(
                    page_document(
                        url=final_url,
                        title=title,
                        text=text,
                        query=query,
                        index=index,
                    )
                )
                packets.append(
                    {
                        "type": "browser_tool_result",
                        "tool": "browser_navigate",
                        "status": "completed",
                        "summary": f"Read {title}",
                        "url": final_url,
                        "title": title,
                    }
                )

            return BrowserSearchResult(documents=documents, packets=packets)

    async def open_urls(self, urls: list[str], *, query: str) -> BrowserControlResult:
        async with self._lock:
            packets: list[dict[str, Any]] = []
            documents: list[dict[str, Any]] = []
            for index, url in enumerate(urls[:MAX_RESULT_COUNT], start=1):
                target = canonicalize_result_url(url)
                packets.append(
                    {
                        "type": "browser_tool_start",
                        "tool": "browser_navigate",
                        "summary": f"Opening {target}",
                        "arguments": {"url": target},
                    }
                )
                await self._call_tool("browser_navigate", {"url": target})
                page_payload = await self._evaluate_json(
                    """() => ({
                      title: document.title,
                      url: location.href,
                      text: document.body ? document.body.innerText : ''
                    })"""
                )
                if not isinstance(page_payload, dict):
                    page_payload = {"title": target, "url": target, "text": ""}
                title = str(page_payload.get("title") or target)
                final_url = str(page_payload.get("url") or target)
                text = str(page_payload.get("text") or "")
                documents.append(
                    page_document(
                        url=final_url,
                        title=title,
                        text=text,
                        query=query,
                        index=index,
                    )
                )
                packets.append(
                    {
                        "type": "browser_tool_result",
                        "tool": "browser_navigate",
                        "status": "completed",
                        "summary": f"Read {title}",
                        "url": final_url,
                        "title": title,
                    }
                )
            return BrowserControlResult(documents=documents, packets=packets)

    async def control(
        self,
        *,
        user_request: str,
        runtime: BaseRuntime,
        model_settings: dict[str, Any],
        model: str,
        temperature: float,
    ) -> BrowserControlResult:
        async with self._lock:
            packets: list[dict[str, Any]] = []
            documents: list[dict[str, Any]] = []
            final_response: str | None = None

            for step_index in range(self.max_steps):
                snapshot_packet = await self._snapshot_packet()
                packets.append(snapshot_packet)
                snapshot_text = snapshot_packet.get("text", "")
                action = await self._plan_next_action(
                    user_request=user_request,
                    snapshot=snapshot_text,
                    runtime=runtime,
                    model_settings=model_settings,
                    model=model,
                    temperature=temperature,
                )

                if "final" in action:
                    final_response = str(action["final"]).strip()
                    if snapshot_text:
                        documents.append(
                            page_document(
                                url=str(snapshot_packet.get("url") or "browser"),
                                title=str(snapshot_packet.get("title") or "Browser snapshot"),
                                text=snapshot_text,
                                query=user_request,
                                index=step_index + 1,
                            )
                        )
                    break

                tool_name = str(action.get("tool") or "")
                arguments = action.get("arguments") if isinstance(action.get("arguments"), dict) else {}
                summary = str(action.get("summary") or tool_name)
                violation = guardrail_violation(user_request, tool_name, arguments)
                if violation:
                    raise BrowserGuardrailError(violation)

                packets.append(
                    {
                        "type": "browser_tool_start",
                        "tool": self._require_tool(tool_name),
                        "summary": summary,
                        "arguments": sanitize_action_arguments(arguments),
                    }
                )
                result_text = await self._call_tool(tool_name, arguments)
                packets.append(
                    {
                        "type": "browser_tool_result",
                        "tool": self._require_tool(tool_name),
                        "status": "completed",
                        "summary": sanitize_text(result_text, 900),
                    }
                )
            else:
                final_response = "I stopped after the configured browser step limit."

            return BrowserControlResult(
                documents=documents,
                packets=packets,
                final_response=final_response,
            )

    async def _plan_next_action(
        self,
        *,
        user_request: str,
        snapshot: str,
        runtime: BaseRuntime,
        model_settings: dict[str, Any],
        model: str,
        temperature: float,
    ) -> dict[str, Any]:
        allowed_tools = sorted(
            tool
            for tool in self._tools
            if tool.startswith("browser_")
            and tool
            not in {
                "browser_install",
                "browser_resize",
                "browser_close",
            }
        )
        prompt = (
            "You control a visible Playwright browser. Return exactly one JSON object.\n"
            "Either {\"final\":\"...\"} when the task is complete, or "
            "{\"tool\":\"browser_navigate|browser_click|browser_type|browser_press_key|"
            "browser_select_option|browser_take_screenshot|browser_pdf_save|"
            "browser_console_messages|browser_network_requests|browser_evaluate\","
            "\"arguments\":{...},\"summary\":\"short user-visible action\"}.\n"
            "Only use these tools: "
            + ", ".join(allowed_tools)
            + "\nDo not include secrets, cookies, localStorage, or auth headers.\n\n"
            f"User request:\n{user_request}\n\nBrowser snapshot:\n{snapshot}"
        )
        chunks: list[str] = []
        async for chunk in runtime.stream_chat(
            base_url=model_settings["llm_base_url"],
            model=model,
            system_prompt="Return only valid JSON for the next browser action.",
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            think=False,
        ):
            chunks.append(chunk.get("content", ""))
        action = parse_action_json("".join(chunks))
        if "tool" in action:
            self._require_tool(str(action["tool"]))
        return action


def parse_action_json(value: str) -> dict[str, Any]:
    stripped = value.strip()
    match = re.search(r"\{.*\}", stripped, re.DOTALL)
    if match:
        stripped = match.group(0)
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise BrowserMCPError("The model did not return a valid browser action.") from exc
    if not isinstance(parsed, dict) or not ("final" in parsed or "tool" in parsed):
        raise BrowserMCPError("The model did not return a browser action or final response.")
    return parsed


def sanitize_action_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    redacted: dict[str, Any] = {}
    for key, value in arguments.items():
        if re.search(r"(?i)(password|token|secret|cookie|authorization)", key):
            redacted[key] = "[REDACTED]"
        elif isinstance(value, str):
            redacted[key] = sanitize_text(value, 400)
        else:
            redacted[key] = value
    return redacted


def parse_snapshot_title_url(snapshot: str) -> tuple[str, str]:
    title = ""
    url = ""
    for line in snapshot.splitlines()[:20]:
        lowered = line.lower()
        if "page title" in lowered or lowered.startswith("title:"):
            title = line.split(":", 1)[-1].strip()
        if "page url" in lowered or lowered.startswith("url:"):
            url = line.split(":", 1)[-1].strip()
    if not url:
        urls = extract_urls(snapshot)
        url = urls[0] if urls else ""
    return title, url


def normalize_google_results(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []

    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, dict):
            continue
        title = sanitize_text(str(item.get("title") or ""), 200).strip()
        url = canonicalize_result_url(str(item.get("url") or ""))
        snippet = sanitize_text(str(item.get("snippet") or ""), 500).strip()
        parsed = urlparse(url)
        if not title or parsed.scheme not in {"http", "https"}:
            continue
        if parsed.netloc.endswith("google.com"):
            continue
        if url in seen:
            continue
        seen.add(url)
        rows.append({"title": title, "url": url, "snippet": snippet})
    return rows
