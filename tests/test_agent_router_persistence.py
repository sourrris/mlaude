from __future__ import annotations

import json
import tempfile
from pathlib import Path

from mlaude.agent import MLaudeAgent
from mlaude.providers.base import LLMResponse
from mlaude.state import SessionDB


def test_agent_persists_tool_calls_usage_and_approval_resume() -> None:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    try:
        db = SessionDB(db_path)
        agent = MLaudeAgent(
            quiet_mode=True,
            session_db=db,
            session_id="session-123",
            reasoning_effort="high",
        )

        responses = [
            LLMResponse(
                content="",
                tool_calls=[
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "terminal", "arguments": json.dumps({"command": "echo hi"})},
                    }
                ],
                usage={"total_tokens": 11},
                reasoning="Need to run a tool.",
            ),
            LLMResponse(
                content="Done https://example.com",
                usage={"total_tokens": 7},
            ),
        ]

        seen_reasoning: list[str | None] = []

        def fake_chat_completions(**kwargs):
            seen_reasoning.append(kwargs.get("reasoning_effort"))
            return responses.pop(0)

        dispatch_results = iter(
            [
                json.dumps({"error": "approval_required", "tool": "terminal", "args": {"command": "echo hi"}}),
                json.dumps({"stdout": "hi", "exit_code": 0}),
            ]
        )

        agent._provider.chat_completions = fake_chat_completions  # type: ignore[method-assign]
        agent._dispatch_tool = lambda name, args, approval_granted=False: next(dispatch_results)
        agent.on_approval_request = lambda tool, args: True

        result = agent.run_conversation("latest terminal result")
        assert result["final_response"] == "Done https://example.com"
        assert result["route"] == "fresh_web"
        assert seen_reasoning == ["high", "high"]

        messages = db.get_messages("session-123")
        assert [message["role"] for message in messages] == ["user", "assistant", "tool", "assistant"]
        assert json.loads(messages[1]["tool_calls"])[0]["function"]["name"] == "terminal"
        assert messages[1]["reasoning"] == "Need to run a tool."

        session = db.get_session("session-123")
        assert session is not None
        assert session["total_tokens"] == 18
    finally:
        Path(db_path).unlink(missing_ok=True)
