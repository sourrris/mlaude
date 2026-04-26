"""Tests for the core agent loop (μ1)."""

from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock, patch

from mlaude.agent import IterationBudget, MLaudeAgent


class TestIterationBudget(unittest.TestCase):
    def test_consume_within_budget(self):
        budget = IterationBudget(3)
        assert budget.consume() is True
        assert budget.consume() is True
        assert budget.consume() is True
        assert budget.consume() is False
        assert budget.used == 3
        assert budget.remaining == 0

    def test_refund(self):
        budget = IterationBudget(2)
        budget.consume()
        budget.consume()
        assert budget.remaining == 0
        budget.refund()
        assert budget.remaining == 1
        assert budget.consume() is True


class TestMLaudeAgentInit(unittest.TestCase):
    def test_defaults(self):
        agent = MLaudeAgent()
        assert agent.platform == "cli"
        assert agent.max_iterations == 50
        assert agent.iteration_budget.max_total == 50
        assert agent._interrupt_requested is False

    def test_custom_params(self):
        agent = MLaudeAgent(
            base_url="http://example.com:8080",
            model="test-model",
            max_iterations=10,
            platform="telegram",
        )
        assert agent.base_url == "http://example.com:8080"
        assert agent.model == "test-model"
        assert agent.max_iterations == 10
        assert agent.platform == "telegram"


class TestMLaudeAgentLoop(unittest.TestCase):
    """Test the agent conversation loop with mocked LLM calls."""

    def test_simple_chat_no_tools(self):
        """Agent returns final response when LLM gives no tool_calls."""
        agent = MLaudeAgent(quiet_mode=True)

        # Mock LLM to return a plain text response
        agent._call_llm = MagicMock(return_value={
            "role": "assistant",
            "content": "Hello! How can I help you?",
        })

        result = agent.run_conversation("Hi there")
        assert result["final_response"] == "Hello! How can I help you?"
        assert result["iterations_used"] == 1
        assert result["stop_reason"] == "complete"

    def test_tool_call_cycle(self):
        """Agent executes tool calls and loops until text response."""
        agent = MLaudeAgent(quiet_mode=True)

        # First call: LLM wants to use a tool
        # Second call: LLM gives final response
        call_count = 0

        def mock_llm(messages, tools):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [{
                        "id": "call_123",
                        "type": "function",
                        "function": {
                            "name": "test_tool",
                            "arguments": json.dumps({"query": "hello"}),
                        },
                    }],
                }
            else:
                return {
                    "role": "assistant",
                    "content": "I found the answer: hello world!",
                }

        agent._call_llm = mock_llm
        agent._dispatch_tool = MagicMock(
            return_value=json.dumps({"result": "hello world"})
        )

        result = agent.run_conversation("Search for hello")
        assert result["final_response"] == "I found the answer: hello world!"
        assert result["iterations_used"] == 2
        assert result["stop_reason"] == "complete"
        agent._dispatch_tool.assert_called_once()

    def test_budget_exhaustion(self):
        """Agent stops when iteration budget is exhausted."""
        agent = MLaudeAgent(max_iterations=2, quiet_mode=True)

        # LLM always wants more tool calls
        agent._call_llm = MagicMock(return_value={
            "role": "assistant",
            "content": "",
            "tool_calls": [{
                "id": "call_loop",
                "type": "function",
                "function": {
                    "name": "infinite_tool",
                    "arguments": "{}",
                },
            }],
        })
        agent._dispatch_tool = MagicMock(
            return_value=json.dumps({"result": "more"})
        )

        result = agent.run_conversation("Keep going")
        # 2 tool iterations + 1 grace call = 3 calls max, but grace call
        # also returns tool_calls, so budget_exhausted
        assert result["stop_reason"] == "budget_exhausted"

    def test_interrupt(self):
        """Agent stops when interrupt is requested."""
        agent = MLaudeAgent(quiet_mode=True)
        agent._interrupt_requested = True

        result = agent.run_conversation("This should be interrupted")
        assert result["stop_reason"] == "interrupted"
        assert result["iterations_used"] == 0

    def test_chat_simple_interface(self):
        """agent.chat() returns just the string."""
        agent = MLaudeAgent(quiet_mode=True)
        agent._call_llm = MagicMock(return_value={
            "role": "assistant",
            "content": "Simple response",
        })

        response = agent.chat("Hello")
        assert response == "Simple response"


if __name__ == "__main__":
    unittest.main()
