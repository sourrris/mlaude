"""Local LLM provider — LM Studio, Ollama, and any OpenAI-compatible server.

Handles the ``/v1/chat/completions`` endpoint that both LM Studio and Ollama
expose.  This is the primary provider for local development.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Iterator

import httpx

from mlaude.providers.base import BaseProvider, LLMResponse

logger = logging.getLogger(__name__)


class LocalProvider(BaseProvider):
    """Provider for OpenAI-compatible local APIs (LM Studio, Ollama, etc.)."""

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
            reasoning=str(message.get("reasoning", "") or ""),
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
        """List models available from the local server."""
        url = f"{self.base_url}/v1/models"
        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(url, headers=self._headers())
                resp.raise_for_status()
                data = resp.json()
                models = data.get("data", [])
                return [m.get("id", "") for m in models if m.get("id")]
        except Exception as e:
            logger.warning("Failed to list models from %s: %s", self.base_url, e)
            return []
