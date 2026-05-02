"""HuggingFace Inference API provider — free tier for many models.

Uses the OpenAI-compatible API at ``api-inference.huggingface.co/v1``.
"""

from __future__ import annotations

import logging
from typing import Any

from mlaude.providers.local import LocalProvider

logger = logging.getLogger(__name__)


class HuggingFaceProvider(LocalProvider):
    """Provider for HuggingFace Inference API."""

    HF_BASE = "https://api-inference.huggingface.co/v1"

    def __init__(self, api_key: str = "", default_model: str = "meta-llama/Meta-Llama-3.1-8B-Instruct", **kwargs):
        super().__init__(
            base_url=self.HF_BASE,
            api_key=api_key,
            default_model=default_model,
            **kwargs,
        )

    def _headers(self) -> dict[str, str]:
        headers = super()._headers()
        headers["User-Agent"] = "mlaude/0.3.0"
        return headers
