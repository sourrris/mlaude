"""Anthropic provider — Claude API access.

Translates between OpenAI message format (used internally) and the
Anthropic Messages API format.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Iterator

import httpx

from mlaude.providers.base import BaseProvider, LLMResponse

logger = logging.getLogger(__name__)


class AnthropicProvider(BaseProvider):
    """Provider for Anthropic Claude API."""

    API_BASE = "https://api.anthropic.com"

    def __init__(self, api_key: str = "", default_model: str = "claude-sonnet-4-20250514", **kwargs):
        super().__init__(
            base_url=self.API_BASE,
            api_key=api_key,
            default_model=default_model,
            **kwargs,
        )

    def _anthropic_headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
        }

    def _to_anthropic_messages(self, messages: list[dict]) -> tuple[str, list[dict]]:
        """Convert OpenAI-format messages to Anthropic format.

        Returns (system_prompt, anthropic_messages).
        """
        system = ""
        anthropic_msgs: list[dict] = []

        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")

            if role == "system":
                system = content
            elif role == "user":
                anthropic_msgs.append({"role": "user", "content": content})
            elif role == "assistant":
                if msg.get("tool_calls"):
                    # Convert tool_calls to Anthropic tool_use blocks
                    blocks: list[dict] = []
                    if content:
                        blocks.append({"type": "text", "text": content})
                    for tc in msg["tool_calls"]:
                        fn = tc.get("function", {})
                        args_str = fn.get("arguments", "{}")
                        try:
                            args = json.loads(args_str) if isinstance(args_str, str) else args_str
                        except json.JSONDecodeError:
                            args = {}
                        blocks.append({
                            "type": "tool_use",
                            "id": tc.get("id", f"toolu_{uuid.uuid4().hex[:12]}"),
                            "name": fn.get("name", ""),
                            "input": args,
                        })
                    anthropic_msgs.append({"role": "assistant", "content": blocks})
                else:
                    anthropic_msgs.append({"role": "assistant", "content": content})
            elif role == "tool":
                anthropic_msgs.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": msg.get("tool_call_id", ""),
                        "content": content,
                    }],
                })

        return system, anthropic_msgs

    def _to_anthropic_tools(self, tools: list[dict]) -> list[dict]:
        """Convert OpenAI-format tool schemas to Anthropic format."""
        result = []
        for tool in tools:
            fn = tool.get("function", {})
            result.append({
                "name": fn.get("name", ""),
                "description": fn.get("description", ""),
                "input_schema": fn.get("parameters", {}),
            })
        return result

    def chat_completions(
        self,
        model: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float = 0.2,
        **kwargs: Any,
    ) -> LLMResponse:
        url = f"{self.base_url}/v1/messages"
        system, anthropic_msgs = self._to_anthropic_messages(messages)

        payload: dict[str, Any] = {
            "model": model or self.default_model,
            "messages": anthropic_msgs,
            "max_tokens": kwargs.get("max_tokens", 8192),
            "temperature": temperature,
        }
        if system:
            payload["system"] = system
        if tools:
            payload["tools"] = self._to_anthropic_tools(tools)

        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(url, json=payload, headers=self._anthropic_headers())
            resp.raise_for_status()
            data = resp.json()

        # Parse response
        content_text = ""
        tool_calls: list[dict] = []

        for block in data.get("content", []):
            if block.get("type") == "text":
                content_text += block.get("text", "")
            elif block.get("type") == "tool_use":
                tool_calls.append({
                    "id": block.get("id", f"toolu_{uuid.uuid4().hex[:12]}"),
                    "type": "function",
                    "function": {
                        "name": block.get("name", ""),
                        "arguments": json.dumps(block.get("input", {})),
                    },
                })

        usage = data.get("usage", {})

        return LLMResponse(
            content=content_text,
            tool_calls=tool_calls if tool_calls else None,
            finish_reason=data.get("stop_reason", ""),
            model=data.get("model", model),
            usage={
                "prompt_tokens": usage.get("input_tokens", 0),
                "completion_tokens": usage.get("output_tokens", 0),
                "total_tokens": (
                    usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
                ),
            },
        )

    def stream_chat(
        self,
        model: str,
        messages: list[dict],
        temperature: float = 0.2,
        **kwargs: Any,
    ) -> Iterator[dict]:
        url = f"{self.base_url}/v1/messages"
        system, anthropic_msgs = self._to_anthropic_messages(messages)

        payload: dict[str, Any] = {
            "model": model or self.default_model,
            "messages": anthropic_msgs,
            "max_tokens": kwargs.get("max_tokens", 8192),
            "temperature": temperature,
            "stream": True,
        }
        if system:
            payload["system"] = system

        with httpx.Client(timeout=self.timeout) as client:
            with client.stream("POST", url, json=payload, headers=self._anthropic_headers()) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines():
                    if not line.startswith("data: "):
                        continue
                    try:
                        event = json.loads(line[6:])
                        if event.get("type") == "content_block_delta":
                            delta = event.get("delta", {})
                            if delta.get("type") == "text_delta":
                                yield {"content": delta.get("text", "")}
                            elif delta.get("type") == "thinking_delta":
                                yield {"thinking": delta.get("thinking", "")}
                    except json.JSONDecodeError:
                        continue
