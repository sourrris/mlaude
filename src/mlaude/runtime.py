from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import TypedDict

import ollama

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

    async def stream_chat(
        self,
        *,
        base_url: str,
        model: str,
        system_prompt: str,
        messages: list[dict[str, str]],
        temperature: float,
    ) -> AsyncIterator[ChatChunk]:
        raise NotImplementedError


class OllamaRuntime(BaseRuntime):
    async def discover_models(self, base_url: str) -> list[str]:
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

    async def stream_chat(
        self,
        *,
        base_url: str,
        model: str,
        system_prompt: str,
        messages: list[dict[str, str]],
        temperature: float,
    ) -> AsyncIterator[ChatChunk]:
        client = ollama.AsyncClient(host=base_url)
        full_messages = [{"role": "system", "content": system_prompt}, *messages]
        try:
            stream = await client.chat(
                model=model,
                messages=full_messages,
                stream=True,
                think=True,
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


def build_runtime() -> BaseRuntime:
    if ENABLE_TEST_RUNTIME:
        return MockRuntime()
    return OllamaRuntime()
