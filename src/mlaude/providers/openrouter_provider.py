"""OpenRouter provider — model aggregator with 200+ models.

Uses the standard OpenAI-compatible API at ``openrouter.ai/api/v1``.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from mlaude.providers.local import LocalProvider

logger = logging.getLogger(__name__)


class OpenRouterProvider(LocalProvider):
    """Provider for OpenRouter (openrouter.ai).

    Inherits from LocalProvider since OpenRouter exposes an OpenAI-compatible
    API.  Adds OpenRouter-specific headers and model listing.
    """

    OPENROUTER_BASE = "https://openrouter.ai/api/v1"

    def __init__(self, api_key: str = "", default_model: str = "openai/gpt-4o", **kwargs):
        super().__init__(
            base_url=self.OPENROUTER_BASE,
            api_key=api_key,
            default_model=default_model,
            **kwargs,
        )

    def _headers(self) -> dict[str, str]:
        headers = super()._headers()
        headers["HTTP-Referer"] = "https://github.com/sourrris/mlaude"
        headers["X-Title"] = "mlaude"
        return headers

    def list_models(self) -> list[str]:
        url = f"{self.base_url}/models"
        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(url, headers=self._headers())
                resp.raise_for_status()
                data = resp.json()
                return [m.get("id", "") for m in data.get("data", []) if m.get("id")]
        except Exception as e:
            logger.warning("Failed to list OpenRouter models: %s", e)
            return []
