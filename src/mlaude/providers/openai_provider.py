"""OpenAI provider — direct OpenAI API access.

Uses the ``openai`` SDK for robust handling of streaming, tool calls,
and error recovery.  Falls back to httpx if the SDK isn't installed.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Iterator

import httpx

from mlaude.providers.base import BaseProvider, LLMResponse

logger = logging.getLogger(__name__)


class OpenAIProvider(BaseProvider):
    """Provider for OpenAI API (gpt-4o, o3, etc.)."""

    def __init__(self, api_key: str = "", default_model: str = "gpt-4o", **kwargs):
        super().__init__(
            base_url="https://api.openai.com",
            api_key=api_key,
            default_model=default_model,
            **kwargs,
        )

    def chat_completions(
        self,
        model: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float = 0.2,
        **kwargs: Any,
    ) -> LLMResponse:
        url = f"{self.base_url}/v1/chat/completions"
        payload: dict[str, Any] = {
            "model": model or self.default_model,
            "messages": messages,
            "temperature": temperature,
        }
        self._apply_reasoning_effort(payload, kwargs.get("reasoning_effort"))
        if tools:
            payload["tools"] = tools

        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(url, json=payload, headers=self._headers())
            resp.raise_for_status()
            data = resp.json()

        choice = data.get("choices", [{}])[0]
        message = choice.get("message", {})
        usage = data.get("usage", {})

        return LLMResponse(
            content=message.get("content", "") or "",
            tool_calls=self._parse_tool_calls(message.get("tool_calls")),
            finish_reason=choice.get("finish_reason", ""),
            model=data.get("model", model),
            usage={
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
            },
            raw_message=message,
        )

    def stream_chat(
        self,
        model: str,
        messages: list[dict],
        temperature: float = 0.2,
        **kwargs: Any,
    ) -> Iterator[dict]:
        url = f"{self.base_url}/v1/chat/completions"
        payload: dict[str, Any] = {
            "model": model or self.default_model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
        }

        with httpx.Client(timeout=self.timeout) as client:
            with client.stream("POST", url, json=payload, headers=self._headers()) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines():
                    if not line.startswith("data: "):
                        continue
                    data_str = line[6:].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                        delta = chunk.get("choices", [{}])[0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            yield {"content": content}
                    except json.JSONDecodeError:
                        continue

    def list_models(self) -> list[str]:
        url = f"{self.base_url}/v1/models"
        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(url, headers=self._headers())
                resp.raise_for_status()
                data = resp.json()
                return [
                    m["id"] for m in data.get("data", [])
                    if m.get("id", "").startswith("gpt-") or m.get("id", "").startswith("o")
                ]
        except Exception:
            return []
