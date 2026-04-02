"""Async Ollama streaming provider."""

import datetime
from collections.abc import AsyncIterator

import ollama

from mlaude.config import OLLAMA_MODEL, OLLAMA_URL, SOUL_PATH


def load_system_prompt() -> str:
    soul = SOUL_PATH.read_text() if SOUL_PATH.exists() else "You are a helpful assistant."
    now = datetime.datetime.now().strftime("%A, %B %-d, %Y at %H:%M")
    return f"{soul.strip()}\n\nCurrent date and time: {now}"


class OllamaProvider:
    def __init__(self):
        self.client = ollama.AsyncClient(host=OLLAMA_URL)

    async def stream(
        self, system: str, messages: list[dict]
    ) -> AsyncIterator[str]:
        all_messages = [{"role": "system", "content": system}] + messages
        response = await self.client.chat(
            model=OLLAMA_MODEL,
            messages=all_messages,
            stream=True,
        )
        async for chunk in response:
            token = chunk.message.content
            if token:
                yield token

    async def generate_title(self, user_msg: str, assistant_msg: str) -> str:
        prompt = (
            f"Summarize this conversation in exactly 4 words. "
            f"No punctuation, no quotes.\n\n"
            f"User: {user_msg[:200]}\nAssistant: {assistant_msg[:200]}"
        )
        response = await self.client.chat(
            model=OLLAMA_MODEL,
            messages=[{"role": "user", "content": prompt}],
        )
        title = response.message.content.strip().strip('"').strip("'")
        return title[:60]

    async def check_status(self) -> dict:
        try:
            resp = await self.client.list()
            models = [m.model for m in resp.models]
            available = any(OLLAMA_MODEL in m for m in models)
            return {"running": True, "model_available": available, "models": models}
        except Exception as e:
            return {"running": False, "model_available": False, "error": str(e)}
