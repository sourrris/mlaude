"""Together AI provider — free credits on signup.

Uses the OpenAI-compatible API at ``api.together.xyz/v1``.
"""

from __future__ import annotations

import logging

from mlaude.providers.local import LocalProvider

logger = logging.getLogger(__name__)


class TogetherProvider(LocalProvider):
    """Provider for Together AI (together.ai)."""

    TOGETHER_BASE = "https://api.together.xyz/v1"

    def __init__(self, api_key: str = "", default_model: str = "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo", **kwargs):
        super().__init__(
            base_url=self.TOGETHER_BASE,
            api_key=api_key,
            default_model=default_model,
            **kwargs,
        )
