"""Tests for provider system (μ4)."""

from __future__ import annotations

import unittest

from mlaude.providers.base import LLMResponse
from mlaude.providers.registry import detect_provider, create_provider
from mlaude.providers.local import LocalProvider
from mlaude.providers.openai_provider import OpenAIProvider
from mlaude.providers.anthropic_provider import AnthropicProvider
from mlaude.providers.openrouter_provider import OpenRouterProvider


class TestDetectProvider(unittest.TestCase):
    def test_local_urls(self):
        assert detect_provider("http://localhost:1234") == "local"
        assert detect_provider("http://127.0.0.1:11434") == "local"
        assert detect_provider("http://0.0.0.0:8080") == "local"

    def test_openai(self):
        assert detect_provider("https://api.openai.com/v1") == "openai"

    def test_anthropic(self):
        assert detect_provider("https://api.anthropic.com") == "anthropic"

    def test_openrouter(self):
        assert detect_provider("https://openrouter.ai/api/v1") == "openrouter"

    def test_empty(self):
        assert detect_provider("") == "local"

    def test_unknown(self):
        assert detect_provider("https://my-proxy.example.com") == "local"


class TestCreateProvider(unittest.TestCase):
    def test_local_provider(self):
        p = create_provider(provider="local", base_url="http://localhost:1234")
        assert isinstance(p, LocalProvider)

    def test_openai_provider(self):
        p = create_provider(provider="openai", api_key="test-key")
        assert isinstance(p, OpenAIProvider)

    def test_anthropic_provider(self):
        p = create_provider(provider="anthropic", api_key="test-key")
        assert isinstance(p, AnthropicProvider)

    def test_openrouter_provider(self):
        p = create_provider(provider="openrouter", api_key="test-key")
        assert isinstance(p, OpenRouterProvider)

    def test_auto_detect(self):
        p = create_provider(base_url="https://api.openai.com/v1", api_key="k")
        assert isinstance(p, OpenAIProvider)


class TestLLMResponse(unittest.TestCase):
    def test_to_message_simple(self):
        r = LLMResponse(content="Hello!")
        msg = r.to_message()
        assert msg["role"] == "assistant"
        assert msg["content"] == "Hello!"
        assert "tool_calls" not in msg

    def test_to_message_with_tools(self):
        r = LLMResponse(
            content="",
            tool_calls=[{"id": "call_1", "type": "function", "function": {
                "name": "test", "arguments": "{}"
            }}],
        )
        msg = r.to_message()
        assert len(msg["tool_calls"]) == 1

    def test_to_message_with_reasoning(self):
        r = LLMResponse(content="Answer", reasoning="Let me think...")
        msg = r.to_message()
        assert msg["reasoning"] == "Let me think..."


class TestAnthropicMessageConversion(unittest.TestCase):
    """Test Anthropic format translation."""

    def test_to_anthropic_messages(self):
        provider = AnthropicProvider(api_key="test")
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
            {"role": "user", "content": "How are you?"},
        ]
        system, anthropic_msgs = provider._to_anthropic_messages(messages)
        assert system == "You are helpful."
        assert len(anthropic_msgs) == 3
        assert anthropic_msgs[0]["role"] == "user"
        assert anthropic_msgs[1]["role"] == "assistant"
        assert anthropic_msgs[2]["role"] == "user"

    def test_tool_calls_conversion(self):
        provider = AnthropicProvider(api_key="test")
        messages = [
            {"role": "assistant", "content": "", "tool_calls": [{
                "id": "call_1",
                "function": {"name": "read_file", "arguments": '{"path": "test.py"}'},
            }]},
            {"role": "tool", "tool_call_id": "call_1", "content": '{"content": "..."}'},
        ]
        _, anthropic_msgs = provider._to_anthropic_messages(messages)
        # Assistant message should have tool_use blocks
        assert anthropic_msgs[0]["role"] == "assistant"
        blocks = anthropic_msgs[0]["content"]
        assert any(b["type"] == "tool_use" for b in blocks)
        # Tool result should be user message with tool_result block
        assert anthropic_msgs[1]["role"] == "user"


if __name__ == "__main__":
    unittest.main()
