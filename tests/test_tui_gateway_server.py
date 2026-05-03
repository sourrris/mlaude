from __future__ import annotations

import tempfile

from mlaude.state import SessionDB
from mlaude.tui_gateway.server import GatewayServer, GatewayState, PendingApproval


class _FakeTransport:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []
        self.results: list[tuple[object, object]] = []
        self.errors: list[tuple[object, int, str]] = []

    def send_event(self, method: str, params: dict | None = None) -> None:
        self.events.append((method, params or {}))

    def send_result(self, request_id, result) -> None:
        self.results.append((request_id, result))

    def send_error(self, request_id, code: int, message: str, data=None) -> None:
        self.errors.append((request_id, code, message))

    def serve(self, handler) -> None:
        return None


class _FakeAgent:
    def __init__(self) -> None:
        self.session_id = "gateway-session"
        self.provider_name = "local"
        self.system_prompt = "system prompt"
        self.reasoning_effort = "medium"
        self.interrupt_requested = False
        self.on_event = None
        self.on_tool_start = None
        self.on_tool_end = None

    def request_interrupt(self) -> None:
        self.interrupt_requested = True

    def run_conversation(self, user_message: str, conversation_history: list[dict]) -> dict:
        if self.on_event:
            self.on_event({"type": "message.delta", "role": "assistant", "delta": "hel"})
            self.on_event({"type": "message.complete", "role": "assistant", "content": "hello"})
            self.on_event({"type": "reasoning.delta", "delta": "think"})
            self.on_event({"type": "reasoning.available", "content": "think"})
        if self.on_tool_start:
            self.on_tool_start("terminal", {"command": "echo hi"})
        if self.on_tool_end:
            self.on_tool_end("terminal", "ok")
        return {
            "final_response": "hello",
            "messages": [
                {"role": "user", "content": user_message},
                {"role": "assistant", "content": "hello"},
            ],
            "iterations_used": 1,
            "stop_reason": "complete",
        }


def _make_server() -> tuple[GatewayServer, GatewayState, _FakeTransport]:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name
    db = SessionDB(db_path)
    state = GatewayState(db=db)
    transport = _FakeTransport()
    server = GatewayServer(transport, state=state)
    return server, state, transport


def test_slash_catalog_returns_commands(monkeypatch) -> None:
    monkeypatch.setattr("mlaude.tui_gateway.server.discover_tools", lambda: None)
    server, _, _ = _make_server()
    result = server._dispatch("slash.catalog", {})
    assert any(command["name"] == "help" for command in result["commands"])


def test_session_send_streams_gateway_events(monkeypatch) -> None:
    monkeypatch.setattr("mlaude.tui_gateway.server.discover_tools", lambda: None)
    server, state, transport = _make_server()
    fake_agent = _FakeAgent()
    state.agent = fake_agent
    state.session_id = fake_agent.session_id
    state.db.create_session(session_id=fake_agent.session_id, model="fake")

    result = server._dispatch("session.send", {"text": "hi"})
    assert result["accepted"] is True

    assert state.worker is not None
    state.worker.join(timeout=2)

    event_names = [name for name, _ in transport.events]
    assert "message.delta" in event_names
    assert "message.complete" in event_names
    assert "reasoning.delta" in event_names
    assert "reasoning.available" in event_names
    assert "tool.start" in event_names
    assert "tool.complete" in event_names
    assert state.last_stop_reason == "complete"


def test_approval_respond_releases_pending(monkeypatch) -> None:
    monkeypatch.setattr("mlaude.tui_gateway.server.discover_tools", lambda: None)
    server, state, _ = _make_server()
    pending = PendingApproval(tool_name="terminal", tool_args={"command": "echo hi"})
    state.pending_approval = pending

    result = server._dispatch("approval.respond", {"approve": True})

    assert result == {"ok": True}
    assert pending.granted is True
    assert pending.event.is_set() is True


def test_logs_tail_returns_latest_log(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("mlaude.tui_gateway.server.discover_tools", lambda: None)
    monkeypatch.setattr("mlaude.tui_gateway.server.LOGS_DIR", tmp_path)
    (tmp_path / "mlaude.log").write_text("a\nb\nc\n", encoding="utf-8")
    server, _, _ = _make_server()

    result = server._dispatch("logs.tail", {"limit": 2})

    assert result["path"].endswith("mlaude.log")
    assert result["content"] == "b\nc"
