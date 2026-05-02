"""Provider registry — auto-detection, instantiation, and failover.

Expanded with NVIDIA, DeepSeek, Groq, Together, Google Gemini, HuggingFace
providers plus aliases.
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

_CLOUD_PATTERNS: dict[str, str] = {
    "api.openai.com": "openai",
    "api.anthropic.com": "anthropic",
    "openrouter.ai": "openrouter",
    "generativelanguage.googleapis.com": "google",
    "integrate.api.nvidia.com": "nvidia",
    "api.deepseek.com": "deepseek",
    "api.groq.com": "groq",
    "api.together.xyz": "together",
    "api-inference.huggingface.co": "huggingface",
}

_LOCAL_PATTERNS = {"localhost", "127.0.0.1", "0.0.0.0", "host.docker.internal"}

# Aliases — maps human-friendly names to canonical provider IDs
ALIASES: dict[str, str] = {
    # nvidia
    "nim": "nvidia",
    "nvidia-nim": "nvidia",
    "build-nvidia": "nvidia",
    "nemotron": "nvidia",
    # deepseek
    "deep-seek": "deepseek",
    # groq
    "groqcloud": "groq",
    # together
    "together-ai": "together",
    "togetherai": "together",
    # google
    "gemini": "google",
    "google-gemini": "google",
    # huggingface
    "hf": "huggingface",
    "hugging-face": "huggingface",
    # openai
    "gpt": "openai",
    "chatgpt": "openai",
    # anthropic
    "claude": "anthropic",
    # openrouter
    "or": "openrouter",
    # local
    "lmstudio": "local",
    "lm-studio": "local",
    "ollama": "local",
    "vllm": "local",
    "llamacpp": "local",
    "llama.cpp": "local",
}


def normalize_provider(name: str) -> str:
    """Resolve aliases and normalise casing to a canonical provider id."""
    key = name.strip().lower()
    return ALIASES.get(key, key)


def detect_provider(base_url: str) -> str:
    """Auto-detect provider from a base URL."""
    if not base_url:
        return "local"

    parsed = urlparse(base_url)
    host = (parsed.hostname or "").lower()

    for pattern, provider in _CLOUD_PATTERNS.items():
        if pattern in host:
            return provider

    if host in _LOCAL_PATTERNS or host.endswith(".local"):
        return "local"

    return "local"


# ---------------------------------------------------------------------------
# API key resolution
# ---------------------------------------------------------------------------

_KEY_ENV_VARS: dict[str, list[str]] = {
    "openai": ["OPENAI_API_KEY"],
    "anthropic": ["ANTHROPIC_API_KEY"],
    "openrouter": ["OPENROUTER_API_KEY"],
    "google": ["GOOGLE_API_KEY", "GEMINI_API_KEY"],
    "nvidia": ["NVIDIA_API_KEY", "NGC_API_KEY"],
    "deepseek": ["DEEPSEEK_API_KEY"],
    "groq": ["GROQ_API_KEY"],
    "together": ["TOGETHER_API_KEY"],
    "huggingface": ["HF_TOKEN", "HUGGINGFACE_API_KEY"],
    "local": ["MLAUDE_API_KEY"],
}


def resolve_api_key(provider: str, explicit_key: str = "") -> str:
    if explicit_key:
        return explicit_key
    for var in _KEY_ENV_VARS.get(provider, []):
        val = os.environ.get(var, "").strip()
        if val:
            return val
    return ""


# ---------------------------------------------------------------------------
# Provider display labels
# ---------------------------------------------------------------------------

PROVIDER_LABELS: dict[str, str] = {
    "local": "Local (LM Studio / Ollama)",
    "openai": "OpenAI",
    "anthropic": "Anthropic",
    "openrouter": "OpenRouter",
    "google": "Google Gemini",
    "nvidia": "NVIDIA NIM",
    "deepseek": "DeepSeek",
    "groq": "Groq",
    "together": "Together AI",
    "huggingface": "HuggingFace",
}


def get_provider_label(provider: str) -> str:
    canonical = normalize_provider(provider)
    return PROVIDER_LABELS.get(canonical, canonical)


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
    """Create a provider instance."""
    if provider is None:
        provider = detect_provider(base_url)
    else:
        provider = normalize_provider(provider)

    key = resolve_api_key(provider, api_key)

    if provider == "openai":
        from mlaude.providers.openai_provider import OpenAIProvider
        return OpenAIProvider(api_key=key, default_model=default_model or "gpt-4o", **kwargs)

    if provider == "anthropic":
        from mlaude.providers.anthropic_provider import AnthropicProvider
        return AnthropicProvider(api_key=key, default_model=default_model or "claude-sonnet-4-20250514", **kwargs)

    if provider == "openrouter":
        from mlaude.providers.openrouter_provider import OpenRouterProvider
        return OpenRouterProvider(api_key=key, default_model=default_model or "openai/gpt-4o", **kwargs)

    if provider == "nvidia":
        from mlaude.providers.nvidia_provider import NvidiaProvider
        return NvidiaProvider(api_key=key, default_model=default_model or "meta/llama-3.1-8b-instruct", **kwargs)

    if provider == "deepseek":
        from mlaude.providers.deepseek_provider import DeepSeekProvider
        return DeepSeekProvider(api_key=key, default_model=default_model or "deepseek-chat", **kwargs)

    if provider == "groq":
        from mlaude.providers.groq_provider import GroqProvider
        return GroqProvider(api_key=key, default_model=default_model or "llama-3.1-8b-instant", **kwargs)

    if provider == "together":
        from mlaude.providers.together_provider import TogetherProvider
        return TogetherProvider(api_key=key, default_model=default_model or "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo", **kwargs)

    if provider == "google":
        from mlaude.providers.google_provider import GoogleProvider
        return GoogleProvider(api_key=key, default_model=default_model or "gemini-2.0-flash", **kwargs)

    if provider == "huggingface":
        from mlaude.providers.huggingface_provider import HuggingFaceProvider
        return HuggingFaceProvider(api_key=key, default_model=default_model or "meta-llama/Meta-Llama-3.1-8B-Instruct", **kwargs)

    # Default: local (LM Studio / Ollama / any OpenAI-compat)
    from mlaude.providers.local import LocalProvider
    return LocalProvider(
        base_url=base_url or "http://127.0.0.1:11434",
        api_key=key,
        default_model=default_model,
        **kwargs,
    )


def list_providers() -> list[dict[str, str]]:
    """List all known providers with their status."""
    result = []
    for pid, label in PROVIDER_LABELS.items():
        env_vars = _KEY_ENV_VARS.get(pid, [])
        has_key = any(os.environ.get(v, "").strip() for v in env_vars)
        result.append({
            "id": pid,
            "name": label,
            "configured": "✓" if has_key or pid == "local" else "✗",
            "env_vars": ", ".join(env_vars),
        })
    return result
