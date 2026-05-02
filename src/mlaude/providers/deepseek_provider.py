"""DeepSeek provider — free credits on signup.

Uses the OpenAI-compatible API at ``api.deepseek.com``.
"""

from __future__ import annotations

import logging
from typing import Any

from mlaude.providers.local import LocalProvider

logger = logging.getLogger(__name__)


class DeepSeekProvider(LocalProvider):
    """Provider for DeepSeek API."""

    DEEPSEEK_BASE = "https://api.deepseek.com"

    def __init__(self, api_key: str = "", default_model: str = "deepseek-chat", **kwargs):
        super().__init__(
            base_url=self.DEEPSEEK_BASE,
            api_key=api_key,
            default_model=default_model,
            **kwargs,
        )
