"""Base provider interface for LLM API communication.

All providers implement this interface so the agent can switch between
local (LM Studio, Ollama) and cloud (OpenAI, Anthropic, OpenRouter) APIs
seamlessly.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Iterator

logger = logging.getLogger(__name__)


@dataclass
class LLMResponse:
    """Normalized response from an LLM API call."""

    content: str = ""
    tool_calls: list[dict] | None = None
    finish_reason: str = ""
    model: str = ""
    usage: dict[str, int] = field(default_factory=dict)
    reasoning: str = ""

    def to_message(self) -> dict[str, Any]:
        """Convert to OpenAI-format assistant message dict."""
        msg: dict[str, Any] = {
            "role": "assistant",
            "content": self.content,
        }
        if self.tool_calls:
            msg["tool_calls"] = self.tool_calls
        if self.reasoning:
            msg["reasoning"] = self.reasoning
        return msg


class BaseProvider(ABC):
    """Abstract base for LLM providers.

    Each provider knows how to:
    - Call the chat completions API (with tool support)
    - Stream responses
    - List available models
    """

    def __init__(
        self,
        base_url: str,
        api_key: str = "",
        default_model: str = "",
        timeout: float = 300.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.default_model = default_model
        self.timeout = timeout

    @abstractmethod
    def chat_completions(
        self,
        model: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float = 0.2,
        **kwargs: Any,
    ) -> LLMResponse:
        """Synchronous chat completions call."""
        ...

    @abstractmethod
    def stream_chat(
        self,
        model: str,
        messages: list[dict],
        temperature: float = 0.2,
        **kwargs: Any,
    ) -> Iterator[dict]:
        """Stream chat response.  Yields dicts with ``content`` and/or ``thinking`` keys."""
        ...

    def list_models(self) -> list[str]:
        """List available models.  Override in subclass."""
        return []

    @property
    def name(self) -> str:
        """Provider name for display/logging."""
        return self.__class__.__name__.replace("Provider", "").lower()

    def _headers(self) -> dict[str, str]:
        """Build HTTP headers."""
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    @staticmethod
    def _parse_tool_calls(raw: list[dict] | None) -> list[dict] | None:
        """Normalize raw tool_calls from API response."""
        if not raw:
            return None
        result = []
        for tc in raw:
            import uuid
            result.append({
                "id": tc.get("id", f"call_{uuid.uuid4().hex[:8]}"),
                "type": "function",
                "function": {
                    "name": tc.get("function", {}).get("name", ""),
                    "arguments": tc.get("function", {}).get("arguments", "{}"),
                },
            })
        return result
