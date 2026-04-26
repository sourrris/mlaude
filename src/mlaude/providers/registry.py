"""Provider registry — auto-detection, instantiation, and failover.

Detects the appropriate provider from the base URL or explicit config,
manages API keys, and supports failover chains.
"""

from __future__ import annotations

import logging
import os
from typing import Any
from urllib.parse import urlparse

from mlaude.providers.base import BaseProvider

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Provider auto-detection
# ---------------------------------------------------------------------------

# Known cloud provider patterns
_CLOUD_PATTERNS: dict[str, str] = {
    "api.openai.com": "openai",
    "api.anthropic.com": "anthropic",
    "openrouter.ai": "openrouter",
    "generativelanguage.googleapis.com": "google",
}

# Local server patterns
_LOCAL_PATTERNS = {"localhost", "127.0.0.1", "0.0.0.0", "host.docker.internal"}


def detect_provider(base_url: str) -> str:
    """Auto-detect provider from a base URL.

    Returns one of: 'local', 'openai', 'anthropic', 'openrouter', 'google'.
    """
    if not base_url:
        return "local"

    parsed = urlparse(base_url)
    host = (parsed.hostname or "").lower()

    # Check cloud patterns first
    for pattern, provider in _CLOUD_PATTERNS.items():
        if pattern in host:
            return provider

    # Local patterns
    if host in _LOCAL_PATTERNS or host.endswith(".local"):
        return "local"

    # Default to local for unknown URLs (likely a proxy or custom endpoint)
    return "local"


# ---------------------------------------------------------------------------
# API key resolution
# ---------------------------------------------------------------------------

_KEY_ENV_VARS: dict[str, list[str]] = {
    "openai": ["OPENAI_API_KEY"],
    "anthropic": ["ANTHROPIC_API_KEY"],
    "openrouter": ["OPENROUTER_API_KEY"],
    "google": ["GOOGLE_API_KEY", "GEMINI_API_KEY"],
    "local": ["MLAUDE_API_KEY"],
}


def resolve_api_key(provider: str, explicit_key: str = "") -> str:
    """Resolve an API key for a provider.

    Priority: explicit key → env var → empty string.
    """
    if explicit_key:
        return explicit_key

    for var in _KEY_ENV_VARS.get(provider, []):
        val = os.environ.get(var, "").strip()
        if val:
            return val

    return ""


# ---------------------------------------------------------------------------
# Provider instantiation
# ---------------------------------------------------------------------------


def create_provider(
    provider: str | None = None,
    base_url: str = "",
    api_key: str = "",
    default_model: str = "",
    **kwargs: Any,
) -> BaseProvider:
    """Create a provider instance.

    If ``provider`` is not specified, auto-detects from ``base_url``.
    """
    if provider is None:
        provider = detect_provider(base_url)

    key = resolve_api_key(provider, api_key)

    if provider == "openai":
        from mlaude.providers.openai_provider import OpenAIProvider
        return OpenAIProvider(
            api_key=key,
            default_model=default_model or "gpt-4o",
            **kwargs,
        )

    if provider == "anthropic":
        from mlaude.providers.anthropic_provider import AnthropicProvider
        return AnthropicProvider(
            api_key=key,
            default_model=default_model or "claude-sonnet-4-20250514",
            **kwargs,
        )

    if provider == "openrouter":
        from mlaude.providers.openrouter_provider import OpenRouterProvider
        return OpenRouterProvider(
            api_key=key,
            default_model=default_model or "openai/gpt-4o",
            **kwargs,
        )

    # Default: local (LM Studio / Ollama / any OpenAI-compat)
    from mlaude.providers.local import LocalProvider
    return LocalProvider(
        base_url=base_url or "http://127.0.0.1:1234",
        api_key=key,
        default_model=default_model,
        **kwargs,
    )


def create_provider_with_failover(
    primary_provider: str | None = None,
    primary_base_url: str = "",
    primary_api_key: str = "",
    primary_model: str = "",
    fallback_provider: str | None = None,
    fallback_base_url: str = "",
    fallback_api_key: str = "",
    fallback_model: str = "",
) -> tuple[BaseProvider, BaseProvider | None]:
    """Create primary + optional fallback providers.

    Returns (primary, fallback) where fallback may be None.
    """
    primary = create_provider(
        provider=primary_provider,
        base_url=primary_base_url,
        api_key=primary_api_key,
        default_model=primary_model,
    )

    fallback = None
    if fallback_provider or fallback_base_url:
        fallback = create_provider(
            provider=fallback_provider,
            base_url=fallback_base_url,
            api_key=fallback_api_key,
            default_model=fallback_model,
        )

    return primary, fallback
