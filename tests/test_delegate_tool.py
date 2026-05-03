from __future__ import annotations

import json

from mlaude.tools import delegate_tool


class FakeDB:
    def __init__(self, depth: int = 0):
        self.depth = depth
        self.created: list[tuple[str | None, str]] = []

    def get_session_depth(self, session_id: str) -> int:
        del session_id
        return self.depth

    def create_session(self, platform: str, model: str, title: str, parent_session_id: str | None = None) -> str:
        self.created.append((parent_session_id, title))
        return "subagent-session"


def test_delegate_task_enforces_depth_limit(monkeypatch) -> None:
    monkeypatch.setattr(delegate_tool, "SessionDB", lambda: FakeDB(depth=2))
    result = json.loads(delegate_tool._delegate_task(task="summarize", task_id="root"))
    assert result["error"] == "Maximum delegation depth reached."


def test_delegate_task_returns_structured_envelope(monkeypatch) -> None:
    fake_db = FakeDB(depth=0)
    monkeypatch.setattr(delegate_tool, "SessionDB", lambda: fake_db)

    class FakeAgent:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def run_conversation(self, user_message: str, system_message: str):
            del user_message, system_message
            return {
                "final_response": "Summary",
                "iterations_used": 2,
                "stop_reason": "complete",
            }

    import mlaude.agent

    monkeypatch.setattr(mlaude.agent, "MLaudeAgent", FakeAgent)
    result = json.loads(
        delegate_tool._delegate_task(
            task="compare frameworks",
            context="A vs B",
            expected_output="bullet summary",
            allowed_toolsets=["web"],
            task_id="root",
        )
    )
    assert result["status"] == "completed"
    assert result["summary"] == "Summary"
    assert result["session_id"] == "subagent-session"
