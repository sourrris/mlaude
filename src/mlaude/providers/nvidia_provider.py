"""NVIDIA NIM provider — free tier available.

Uses the OpenAI-compatible API at ``integrate.api.nvidia.com/v1``.
Sign up at https://build.nvidia.com for free API credits.
"""

from __future__ import annotations

import logging

from mlaude.providers.local import LocalProvider

logger = logging.getLogger(__name__)


class NvidiaProvider(LocalProvider):
    """Provider for NVIDIA NIM (build.nvidia.com)."""

    NVIDIA_BASE = "https://integrate.api.nvidia.com/v1"

    def __init__(self, api_key: str = "", default_model: str = "meta/llama-3.1-8b-instruct", **kwargs):
        super().__init__(
            base_url=self.NVIDIA_BASE,
            api_key=api_key,
            default_model=default_model,
            **kwargs,
        )

    def _headers(self) -> dict[str, str]:
        headers = super()._headers()
        headers["User-Agent"] = "mlaude/0.3.0"
        return headers
