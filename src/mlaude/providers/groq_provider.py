"""Groq provider — free tier with generous rate limits.

Uses the OpenAI-compatible API at ``api.groq.com/openai/v1``.
"""

from __future__ import annotations

import logging
from typing import Any

from mlaude.providers.local import LocalProvider

logger = logging.getLogger(__name__)


class GroqProvider(LocalProvider):
    """Provider for Groq (groq.com) — ultra-fast inference."""

    GROQ_BASE = "https://api.groq.com/openai/v1"

    def __init__(self, api_key: str = "", default_model: str = "llama-3.1-8b-instant", **kwargs):
        super().__init__(
            base_url=self.GROQ_BASE,
            api_key=api_key,
            default_model=default_model,
            **kwargs,
        )
