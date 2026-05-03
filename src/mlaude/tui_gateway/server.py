from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mlaude.agent import MLaudeAgent
from mlaude.commands import COMMAND_REGISTRY, resolve_command
from mlaude.model_tools import discover_tools
from mlaude.providers.registry import get_provider_label
from mlaude.settings import (
    DEFAULT_CHAT_MODEL,
    DEFAULT_TEMPERATURE,
    LLM_BASE_URL,
    LOGS_DIR,
    get_display_config,
    load_config,
    save_config_value,
)
from mlaude.state import SessionDB
from mlaude.tui_gateway.render import (
    build_transcript,
    render_config,
    render_help,
    render_history,
    render_providers,
    render_sessions,
    render_skills,
    render_skins,
    render_stats,
    render_tools,
    render_toolsets,
)
from mlaude.tui_gateway.transport import JsonRpcTransport

logger = logging.getLogger(__name__)


@dataclass
class PendingApproval:
    tool_name: str
    tool_args: dict[str, Any]
    event: threading.Event = field(default_factory=threading.Event)
    granted: bool = False


@dataclass
class GatewayState:
    db: SessionDB
    model: str = DEFAULT_CHAT_MODEL
    base_url: str = LLM_BASE_URL
    temperature: float = DEFAULT_TEMPERATURE
    provider: str | None = None
    resume_id: str | None = None
    quiet: bool = False
    session_id: str | None = None
    conversation_history: list[dict[str, Any]] = field(default_factory=list)
    last_user_input: str = ""
    last_stop_reason: str = "idle"
    last_iterations: int = 0
    reasoning_mode: str = "medium"
    agent: MLaudeAgent | None = None
    worker: threading.Thread | None = None
    pending_approval: PendingApproval | None = None

    def ensure_agent(self) -> MLaudeAgent:
        if self.agent is not None:
            return self.agent
        self.agent = MLaudeAgent(
            base_url=self.base_url,
            model=self.model,
            temperature=self.temperature,
            quiet_mode=self.quiet,
            provider=self.provider,
            session_db=self.db,
            session_id=self.session_id,
            reasoning_effort=self.reasoning_mode,
        )
        self.session_id = self.agent.session_id
        return self.agent


class GatewayServer:
    def __init__(self, transport: JsonRpcTransport, *, state: GatewayState):
        self.transport = transport
        self.state = state
        self._state_lock = threading.Lock()
        discover_tools()

    def emit(self, method: str, params: dict[str, Any] | None = None) -> None:
        self.transport.send_event(method, params or {})

    def emit_status(self, *, busy: bool, detail: str = "") -> None:
        session = self.state.db.get_session(self.state.session_id or "") or {}
        provider_name = (
            self.state.agent.provider_name
            if self.state.agent is not None
            else (self.state.provider or "local")
        )
        self.emit(
            "status.update",
            {
                "busy": busy,
                "detail": detail,
                "session_id": self.state.session_id or "",
                "model": self.state.model,
                "provider": provider_name,
                "provider_label": get_provider_label(provider_name),
                "iterations": self.state.last_iterations,
                "stop_reason": self.state.last_stop_reason,
                "session_tokens": int(session.get("total_tokens", 0) or 0),
            },
        )

    def _set_agent_callbacks(self, agent: MLaudeAgent) -> None:
        agent.on_tool_start = lambda name, args: self.emit(
            "tool.start", {"name": name, "arguments": args}
        )
        agent.on_tool_end = lambda name, result: self.emit(
            "tool.complete", {"name": name, "result": result}
        )

        def _approval(tool_name: str, tool_args: dict[str, Any]) -> bool:
            pending = PendingApproval(tool_name=tool_name, tool_args=tool_args)
            self.state.pending_approval = pending
            self.emit(
                "approval.request",
                {"tool_name": tool_name, "arguments": tool_args},
            )
            pending.event.wait()
            self.state.pending_approval = None
            return pending.granted

        agent.on_approval_request = _approval
        agent.on_event = self._handle_agent_event

    def _handle_agent_event(self, event: dict[str, Any]) -> None:
        name = str(event.get("type", ""))
        payload = dict(event)
        payload.pop("type", None)
        if name == "message.delta":
            self.emit("message.delta", payload)
        elif name == "message.complete":
            self.emit("message.complete", payload)
        elif name == "reasoning.delta":
            self.emit("reasoning.delta", payload)
        elif name == "reasoning.available":
            self.emit("reasoning.available", payload)
        elif name == "status.update":
            self.emit("status.update", payload)

    def handle_message(self, message: dict[str, Any]) -> None:
        request_id = message.get("id")
        method = message.get("method")
        params = message.get("params", {}) or {}
        try:
            result = self._dispatch(method, params)
        except Exception as exc:
            logger.exception("Gateway handler failed")
            self.emit("gateway.stderr", {"message": str(exc)})
            self.transport.send_error(request_id, -32000, str(exc))
            return
        if request_id is not None:
            self.transport.send_result(request_id, result)

    def _dispatch(self, method: str, params: dict[str, Any]) -> Any:
        if method == "session.new":
            return self._session_new()
        if method == "session.resume":
            return self._session_resume(params.get("session_id"))
        if method == "session.send":
            return self._session_send(str(params.get("text", "") or ""))
        if method == "session.interrupt":
            return self._session_interrupt()
        if method == "slash.catalog":
            return self._slash_catalog()
        if method == "slash.exec":
            return self._slash_exec(str(params.get("text", "") or ""))
        if method == "config.get":
            return self._config_get()
        if method == "config.set":
            return self._config_set(str(params.get("key", "")), params.get("value"))
        if method == "approval.respond":
            return self._approval_respond(bool(params.get("approve")))
        if method == "logs.tail":
            return self._logs_tail(int(params.get("limit", 80) or 80))
        raise ValueError(f"Unknown RPC method: {method}")

    def _session_payload(self) -> dict[str, Any]:
        session_id = self.state.session_id or ""
        return {
            "session_id": session_id,
            "transcript": build_transcript(self.state.db, session_id) if session_id else [],
        }

    def _session_new(self) -> dict[str, Any]:
        self.state.session_id = None
        self.state.conversation_history = []
        self.state.last_user_input = ""
        self.state.last_stop_reason = "new_session"
        self.state.last_iterations = 0
        self.state.agent = None
        agent = self.state.ensure_agent()
        self._set_agent_callbacks(agent)
        self.emit_status(busy=False, detail="New session ready")
        return self._session_payload()

    def _session_resume(self, session_id: str | None) -> dict[str, Any]:
        resolved = session_id or self.state.resume_id or ""
        if resolved:
            resolved = self.state.db.resolve_session_id(resolved) or resolved
            history = self.state.db.get_openai_messages(resolved)
            if history:
                self.state.session_id = resolved
                self.state.conversation_history = [m for m in history if m.get("role") != "system"]
                self.state.agent = None
                agent = self.state.ensure_agent()
                self._set_agent_callbacks(agent)
                self.emit_status(busy=False, detail=f"Resumed {resolved[:12]}")
                return self._session_payload()
        return self._session_new()

    def _session_send(self, text: str) -> dict[str, Any]:
        if not text.strip():
            return {"accepted": False, "reason": "empty"}
        if self.state.worker and self.state.worker.is_alive():
            return {"accepted": False, "reason": "busy"}

        agent = self.state.ensure_agent()
        agent.reasoning_effort = self.state.reasoning_mode
        self._set_agent_callbacks(agent)
        self.state.last_user_input = text
        self.state.last_stop_reason = "running"
        self.emit_status(busy=True, detail="Running")
        should_title = len(self.state.conversation_history) == 0

        def _worker() -> None:
            try:
                result = agent.run_conversation(
                    user_message=text,
                    conversation_history=self.state.conversation_history,
                )
                self.state.conversation_history = [
                    message for message in result.get("messages", []) if message.get("role") != "system"
                ]
                self.state.last_stop_reason = str(result.get("stop_reason", "complete"))
                self.state.last_iterations = int(result.get("iterations_used", 0) or 0)
                if should_title and result.get("final_response"):
                    self.state.db.update_session_title(agent.session_id, text[:60])
                self.emit_status(busy=False, detail=self.state.last_stop_reason)
            except Exception as exc:
                self.state.last_stop_reason = f"error: {exc}"
                self.emit("gateway.stderr", {"message": str(exc)})
                self.emit_status(busy=False, detail=self.state.last_stop_reason)

        self.state.worker = threading.Thread(target=_worker, daemon=True)
        self.state.worker.start()
        return {"accepted": True, "session_id": agent.session_id}

    def _session_interrupt(self) -> dict[str, Any]:
        if self.state.agent is None:
            return {"ok": False, "reason": "no_agent"}
        self.state.agent.request_interrupt()
        self.emit_status(busy=True, detail="Interrupt requested")
        return {"ok": True}

    def _slash_catalog(self) -> dict[str, Any]:
        return {
            "commands": [
                {
                    "name": cmd.name,
                    "description": cmd.description,
                    "category": cmd.category,
                    "aliases": list(cmd.aliases),
                    "args_hint": cmd.args_hint,
                }
                for cmd in COMMAND_REGISTRY
            ]
        }

    def _panel(self, title: str, body: str) -> dict[str, Any]:
        return {"kind": "panel", "title": title, "body": body}

    def _slash_exec(self, text: str) -> dict[str, Any]:
        canonical, args_str = resolve_command(text)
        if not canonical:
            return {"kind": "notice", "level": "error", "body": f"Unknown command: {text}"}
        args = args_str.strip()
        agent = self.state.ensure_agent()

        if canonical == "help":
            return self._panel("Help", render_help())
        if canonical == "tools":
            return self._panel("Tools", render_tools())
        if canonical == "toolsets":
            return self._panel("Toolsets", render_toolsets())
        if canonical == "skills":
            return self._panel("Skills", render_skills())
        if canonical == "sessions":
            return self._panel("Sessions", render_sessions(self.state.db))
        if canonical == "usage":
            session = self.state.db.get_session(agent.session_id) or {}
            return {
                "kind": "notice",
                "level": "info",
                "body": (
                    f"Session {agent.session_id[:12]}… | tokens {session.get('total_tokens', 0):,} | "
                    f"cost ${float(session.get('total_cost', 0.0)):.4f}"
                ),
            }
        if canonical == "config":
            return self._panel(
                "Config",
                render_config(
                    model=self.state.model,
                    base_url=self.state.base_url,
                    temperature=self.state.temperature,
                    provider=self.state.provider or "auto",
                ),
            )
        if canonical == "providers":
            return self._panel("Providers", render_providers())
        if canonical == "history":
            return self._panel("History", render_history(self.state.db, agent.session_id))
        if canonical == "stats":
            return {"kind": "notice", "level": "info", "body": render_stats(self.state.db)}
        if canonical == "version":
            from mlaude.banner import VERSION

            return {"kind": "notice", "level": "info", "body": f"mlaude v{VERSION}"}
        if canonical == "new":
            return {"kind": "session", **self._session_new(), "body": "New session started."}
        if canonical == "resume":
            if not args:
                return self._panel("Sessions", render_sessions(self.state.db))
            return {"kind": "session", **self._session_resume(args or None)}
        if canonical == "model":
            if args:
                self.state.model = args
                self.state.agent = None
                self.state.ensure_agent()
                self.emit_status(busy=False, detail=f"Model set to {args}")
                return {"kind": "notice", "level": "info", "body": f"Model set to: {args}"}
            return {"kind": "notice", "level": "info", "body": f"Current model: {self.state.model}"}
        if canonical == "provider":
            if args:
                self.state.provider = args
                self.state.agent = None
                self.state.conversation_history = []
                self.state.ensure_agent()
                self.emit_status(busy=False, detail=f"Provider set to {args}")
                return {
                    "kind": "notice",
                    "level": "info",
                    "body": f"Provider set to: {get_provider_label(args)} (new session)",
                }
            return self._panel("Providers", render_providers())
        if canonical == "temperature":
            if args:
                self.state.temperature = float(args)
                self.state.agent = None
                self.state.ensure_agent()
                return {
                    "kind": "notice",
                    "level": "info",
                    "body": f"Temperature set to: {self.state.temperature}",
                }
            return {
                "kind": "notice",
                "level": "info",
                "body": f"Current temperature: {self.state.temperature}",
            }
        if canonical == "title":
            if args:
                self.state.db.update_session_title(agent.session_id, args)
                return {"kind": "notice", "level": "info", "body": "Session title updated."}
            session = self.state.db.get_session(agent.session_id) or {}
            return {
                "kind": "notice",
                "level": "info",
                "body": f"Title: {session.get('title', '') or '(untitled)'}",
            }
        if canonical == "compress":
            source_id = agent.session_id
            new_sid = self.state.db.create_continuation_session(source_id)
            self.state.session_id = new_sid
            self.state.conversation_history = []
            self.state.agent = None
            self.state.ensure_agent()
            return {
                "kind": "notice",
                "level": "info",
                "body": f"Compressed context into continuation session {new_sid[:12]}…",
            }
        if canonical == "retry":
            if self.state.last_user_input:
                return {"kind": "send", "text": self.state.last_user_input}
            return {"kind": "notice", "level": "warn", "body": "No prior user message to retry."}
        if canonical == "undo":
            if len(self.state.conversation_history) >= 2:
                self.state.conversation_history = self.state.conversation_history[:-2]
                return {
                    "kind": "notice",
                    "level": "info",
                    "body": "Removed last conversation turn from in-memory context.",
                }
            return {"kind": "notice", "level": "warn", "body": "Not enough context to undo."}
        if canonical == "delete":
            if not args:
                return {"kind": "notice", "level": "warn", "body": "Usage: /delete <session_id>"}
            resolved = self.state.db.resolve_session_id(args)
            if not resolved:
                return {"kind": "notice", "level": "error", "body": f"Session not found: {args}"}
            self.state.db.delete_session(resolved)
            return {"kind": "notice", "level": "info", "body": f"Deleted session {resolved[:12]}…"}
        if canonical == "search":
            if not args:
                return {"kind": "notice", "level": "warn", "body": "Usage: /search <query>"}
            results = self.state.db.search_sessions(args)
            if not results:
                return {"kind": "notice", "level": "info", "body": f"No results for: {args}"}
            body = "\n".join(
                f"{item['id'][:12]}  {item.get('updated_at', '')[:19]}  {item.get('title', '') or '(untitled)'}"
                for item in results
            )
            return self._panel("Search", f"Search: {args}\n\n{body}")
        if canonical == "busy":
            value = args if args in {"on", "off"} else None
            if value:
                save_config_value("display.busy_input_mode", value)
            current = value or get_display_config().get("busy_input_mode", "off")
            return {"kind": "notice", "level": "info", "body": f"Busy input mode: {current}"}
        if canonical == "reasoning":
            if args in {"low", "medium", "high"}:
                self.state.reasoning_mode = args
            return {
                "kind": "notice",
                "level": "info",
                "body": f"Reasoning mode: {self.state.reasoning_mode}",
            }
        if canonical == "details":
            if args in {"on", "off"}:
                save_config_value("display.details_mode", "expanded" if args == "on" else "hidden")
            mode = get_display_config().get("details_mode", "hidden")
            return {"kind": "notice", "level": "info", "body": f"Details mode: {mode}"}
        if canonical == "skin":
            from mlaude.skin_engine import set_active_skin

            if args:
                set_active_skin(args)
                save_config_value("display.skin", args)
                return {"kind": "notice", "level": "info", "body": f"Skin set to: {args}"}
            return self._panel("Skins", render_skins())
        if canonical == "system":
            if args:
                agent.system_prompt = args
                return {"kind": "notice", "level": "info", "body": "System prompt updated."}
            return {"kind": "notice", "level": "info", "body": agent.system_prompt[:200]}
        if canonical == "debug":
            logger.setLevel(logging.DEBUG if logger.level != logging.DEBUG else logging.WARNING)
            return {"kind": "notice", "level": "info", "body": f"Debug: {'on' if logger.level == logging.DEBUG else 'off'}"}
        if canonical == "copy":
            last_msg = next(
                (
                    message["content"]
                    for message in reversed(self.state.conversation_history)
                    if message.get("role") == "assistant" and message.get("content")
                ),
                "",
            )
            return {"kind": "copy", "text": last_msg}
        if canonical == "quit":
            return {"kind": "quit", "body": "Goodbye!"}
        return {"kind": "notice", "level": "error", "body": f"Unhandled command: /{canonical}"}

    def _config_get(self) -> dict[str, Any]:
        config = load_config()
        return {
            "config": config,
            "display": get_display_config(config),
            "model": self.state.model,
            "provider": self.state.provider or "",
            "temperature": self.state.temperature,
        }

    def _config_set(self, key: str, value: Any) -> dict[str, Any]:
        if not key:
            raise ValueError("config key is required")
        save_config_value(key, value)
        return self._config_get()

    def _approval_respond(self, approve: bool) -> dict[str, Any]:
        pending = self.state.pending_approval
        if pending is None:
            return {"ok": False, "reason": "no_pending_approval"}
        pending.granted = approve
        pending.event.set()
        return {"ok": True}

    def _logs_tail(self, limit: int) -> dict[str, Any]:
        log_dir = Path(LOGS_DIR)
        files = sorted(log_dir.glob("*.log"), key=lambda item: item.stat().st_mtime, reverse=True)
        if not files:
            return {"path": "", "content": ""}
        content = files[0].read_text(encoding="utf-8", errors="replace").splitlines()[-limit:]
        return {"path": str(files[0]), "content": "\n".join(content)}

    def serve(self) -> None:
        self.emit(
            "gateway.ready",
            {
                "pid": threading.get_native_id(),
                "resume_id": self.state.resume_id or "",
            },
        )
        self.transport.serve(self.handle_message)
