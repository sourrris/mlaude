from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import TypedDict

import httpx
try:
    import ollama
except ImportError:  # ollama is optional — install with pip install -e ".[ollama]"
    ollama = None  # type: ignore[assignment]

from mlaude.settings import ENABLE_TEST_RUNTIME


class RuntimeErrorInfo(RuntimeError):
    pass


class ChatChunk(TypedDict):
    content: str
    thinking: str


class BaseRuntime:
    async def discover_models(self, base_url: str) -> list[str]:
        raise NotImplementedError

    async def check(self, base_url: str, model: str | None = None) -> dict:
        raise NotImplementedError

    async def load_model(self, base_url: str, model: str) -> dict:
        raise NotImplementedError

    async def download_model(self, base_url: str, model: str) -> dict:
        raise NotImplementedError

    async def get_download_status(self, base_url: str, job_id: str) -> dict:
        raise NotImplementedError

    async def stream_chat(
        self,
        *,
        base_url: str,
        model: str,
        system_prompt: str,
        messages: list[dict[str, str]],
        temperature: float,
        think: bool = True,
    ) -> AsyncIterator[ChatChunk]:
        raise NotImplementedError


class LLMRuntime(BaseRuntime):
    """Runtime for Ollama. Requires: pip install -e '.[ollama]'"""

    def _require_ollama(self) -> None:
        if ollama is None:
            raise RuntimeError("Ollama runtime requires 'ollama' package. Install with: pip install -e '.[ollama]'")

    async def discover_models(self, base_url: str) -> list[str]:
        self._require_ollama()
        client = ollama.AsyncClient(host=base_url)
        response = await client.list()
        return sorted(model.model for model in response.models)

    async def check(self, base_url: str, model: str | None = None) -> dict:
        try:
            models = await self.discover_models(base_url)
            return {
                "running": True,
                "models": models,
                "model_available": model in models if model else True,
            }
        except Exception as exc:  # pragma: no cover - exercised in local runtime
            return {
                "running": False,
                "models": [],
                "model_available": False,
                "error": str(exc),
            }

    async def load_model(self, base_url: str, model: str) -> dict:
        return {"status": "not_supported", "message": "Model loading not supported in Ollama runtime"}

    async def download_model(self, base_url: str, model: str) -> dict:
        return {"status": "not_supported", "message": "Model downloading not supported in Ollama runtime"}

    async def get_download_status(self, base_url: str, job_id: str) -> dict:
        return {"status": "not_supported", "message": "Download status not supported in Ollama runtime"}

    async def stream_chat(
        self,
        *,
        base_url: str,
        model: str,
        system_prompt: str,
        messages: list[dict[str, str]],
        temperature: float,
        think: bool = True,
    ) -> AsyncIterator[ChatChunk]:
        self._require_ollama()
        client = ollama.AsyncClient(host=base_url)
        full_messages = [{"role": "system", "content": system_prompt}, *messages]
        try:
            stream = await client.chat(
                model=model,
                messages=full_messages,
                stream=True,
                think=think,
                options={"temperature": temperature},
            )
        except Exception:
            stream = await client.chat(
                model=model,
                messages=full_messages,
                stream=True,
                options={"temperature": temperature},
            )
        async for chunk in stream:
            content = chunk.message.content or ""
            thinking = chunk.message.thinking or ""
            if content or thinking:
                yield {"content": content, "thinking": thinking}


class LMStudioRuntime(BaseRuntime):
    """Runtime for LM Studio using its OpenAI-compatible API at /v1/*."""

    async def discover_models(self, base_url: str) -> list[str]:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{base_url.rstrip('/')}/v1/models")
            response.raise_for_status()
            data = response.json()
            models = data.get("data", []) if isinstance(data, dict) else data
            return sorted(model.get("id") for model in models if isinstance(model, dict))

    async def check(self, base_url: str, model: str | None = None) -> dict:
        try:
            models = await self.discover_models(base_url)
            return {
                "running": True,
                "models": models,
                "model_available": model in models if model else True,
            }
        except Exception as exc:
            return {
                "running": False,
                "models": [],
                "model_available": False,
                "error": str(exc),
            }

    async def load_model(self, base_url: str, model: str) -> dict:
        return {"status": "not_supported", "message": "Use LM Studio UI to load models"}

    async def download_model(self, base_url: str, model: str) -> dict:
        return {"status": "not_supported", "message": "Use LM Studio UI to download models"}

    async def get_download_status(self, base_url: str, job_id: str) -> dict:
        return {"status": "not_supported", "message": "Use LM Studio UI to check downloads"}

    async def stream_chat(
        self,
        *,
        base_url: str,
        model: str,
        system_prompt: str,
        messages: list[dict[str, str]],
        temperature: float,
        think: bool = True,
    ) -> AsyncIterator[ChatChunk]:
        full_messages = [{"role": "system", "content": system_prompt}, *messages]
        async with httpx.AsyncClient() as client:
            async with client.stream(
                "POST",
                f"{base_url.rstrip('/')}/v1/chat/completions",
                json={
                    "model": model,
                    "messages": full_messages,
                    "temperature": temperature,
                    "stream": True,
                },
                timeout=None,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    line = line.strip()
                    if not line or line == "data: [DONE]":
                        continue
                    if line.startswith("data: "):
                        payload = line[6:]
                        try:
                            chunk = json.loads(payload)
                            delta = chunk.get("choices", [{}])[0].get("delta", {})
                            content_text = delta.get("content", "")
                            reasoning_text = delta.get("reasoning", "")
                            if content_text or reasoning_text:
                                yield {"content": content_text, "thinking": reasoning_text}
                        except json.JSONDecodeError:
                            continue


class MockRuntime(BaseRuntime):
    async def discover_models(self, base_url: str) -> list[str]:  # noqa: ARG002
        return ["mock-chat:latest", "mock-tools:latest"]

    async def check(self, base_url: str, model: str | None = None) -> dict:  # noqa: ARG002
        models = await self.discover_models(base_url)
        return {
            "running": True,
            "models": models,
            "model_available": model in models if model else True,
        }

    async def stream_chat(
        self,
        *,
        base_url: str,  # noqa: ARG002
        model: str,  # noqa: ARG002
        system_prompt: str,  # noqa: ARG002
        messages: list[dict[str, str]],
        temperature: float,  # noqa: ARG002
        think: bool = True,  # noqa: ARG002
    ) -> AsyncIterator[ChatChunk]:
        latest_message = messages[-1]["content"] if messages else ""
        if '"document": 1' in latest_message:
            response = (
                "I found the answer in your local files. "
                "The most relevant passage is cited here [1]. "
                "If you open sources, you can inspect the supporting excerpt."
            )
        elif "PYTHON_RESULT:" in latest_message:
            response = (
                "I used the Python tool and summarized the result above. "
                "The execution output is reflected in this answer."
            )
        else:
            response = (
                "This is a local mock response from the workspace runtime. "
                "It streams tokens the same way the Ollama runtime does."
            )

        for token in response.split(" "):
            await asyncio.sleep(0.01)
            yield {"content": token + " ", "thinking": ""}


def build_runtime(provider: str = "lm-studio") -> BaseRuntime:
    if ENABLE_TEST_RUNTIME:
        return MockRuntime()
    if provider == "ollama":
        return LLMRuntime()
    return LMStudioRuntime()
