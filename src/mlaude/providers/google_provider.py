"""Google Gemini provider — free tier available.

Uses the OpenAI-compatible API at ``generativelanguage.googleapis.com``.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Iterator

import httpx

from mlaude.providers.base import BaseProvider, LLMResponse

logger = logging.getLogger(__name__)


class GoogleProvider(BaseProvider):
    """Provider for Google Gemini API."""

    GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"

    def __init__(self, api_key: str = "", default_model: str = "gemini-2.0-flash", **kwargs):
        super().__init__(
            base_url=self.GEMINI_BASE,
            api_key=api_key,
            default_model=default_model,
            **kwargs,
        )

    def _headers(self) -> dict[str, str]:
        return {"Content-Type": "application/json"}

    def chat_completions(
        self,
        model: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float = 0.2,
        **kwargs: Any,
    ) -> LLMResponse:
        """Use the OpenAI-compatible endpoint Google provides."""
        # Google offers an OpenAI-compat endpoint
        url = f"https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
        payload: dict[str, Any] = {
            "model": model or self.default_model,
            "messages": messages,
            "temperature": temperature,
        }
        if tools:
            payload["tools"] = tools

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(url, json=payload, headers=headers)
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
        )

    def stream_chat(
        self,
        model: str,
        messages: list[dict],
        temperature: float = 0.2,
        **kwargs: Any,
    ) -> Iterator[dict]:
        url = f"https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
        payload: dict[str, Any] = {
            "model": model or self.default_model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        with httpx.Client(timeout=self.timeout) as client:
            with client.stream("POST", url, json=payload, headers=headers) as resp:
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
        url = f"{self.base_url}/models?key={self.api_key}"
        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(url)
                resp.raise_for_status()
                data = resp.json()
                return [
                    m.get("name", "").replace("models/", "")
                    for m in data.get("models", [])
                    if "generateContent" in str(m.get("supportedGenerationMethods", []))
                ]
        except Exception as e:
            logger.warning("Failed to list Gemini models: %s", e)
            return []
