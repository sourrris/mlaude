"""Async Ollama streaming provider with tool-calling support."""

import datetime
import logging
import re
import time
from collections.abc import AsyncIterator

import ollama

from mlaude.config import OLLAMA_MODEL, OLLAMA_URL, SOUL_PATH, MEMORY_PATH
from mlaude.tools_base import ToolEvent, ToolRegistry

logger = logging.getLogger("mlaude")


def _memory_has_content(memory_text: str) -> bool:
    """Return True if MEMORY.md has at least one bullet fact (not just empty section headers)."""
    return bool(re.search(r"^- .+", memory_text, re.MULTILINE))


def load_system_prompt(rag_context: list[dict] | None = None) -> str:
    """Build the system prompt with hierarchical, source-type-aware injection.

    Section order (highest → lowest priority in context window):
      1. SOUL.md — core identity and behavioral rules (always present)
      2. About you — chunks tagged source_type "about" or "behavior"
      3. Your interest context — chunks tagged source_type "interest"
      4. Your memory — persistent facts from MEMORY.md (only if non-empty)
      5. Relevant knowledge — general knowledge chunks
      6. Datetime

    Behavioral and interest context appears before memory and factual knowledge
    so the LLM applies the right behavioral lens before processing other context.
    """
    soul = SOUL_PATH.read_text() if SOUL_PATH.exists() else "You are a helpful assistant."
    now = datetime.datetime.now().strftime("%A, %B %-d, %Y at %H:%M")

    parts = [soul.strip()]

    # Split RAG chunks by source type (dicts may or may not carry source_type)
    about_chunks: list[str] = []
    interest_chunks: list[str] = []
    general_chunks: list[str] = []

    if rag_context:
        for c in rag_context:
            text = c["text"] if isinstance(c, dict) else c
            stype = c.get("source_type", "general") if isinstance(c, dict) else "general"
            if stype in ("about", "behavior"):
                about_chunks.append(text)
            elif stype == "interest":
                interest_chunks.append(text)
            else:
                general_chunks.append(text)

    # About/behavior context — inject first (shapes how to read everything else)
    if about_chunks:
        parts.append("--- Context About You ---\n" + "\n\n".join(about_chunks))

    # Interest context — inject before memory
    if interest_chunks:
        parts.append("--- Your Interest Context ---\n" + "\n\n".join(interest_chunks))

    # Memory — only inject if it has actual facts, not just empty section headers
    if MEMORY_PATH.exists():
        memory = MEMORY_PATH.read_text().strip()
        if memory and _memory_has_content(memory):
            parts.append(f"--- About You (Your Memory) ---\n{memory}")

    # General knowledge — inject last of the context sections
    if general_chunks:
        parts.append("--- Relevant Knowledge ---\n" + "\n\n".join(general_chunks))

    parts.append(f"Current date and time: {now}")

    # Thinking instruction — always appended last so the model reads it as a
    # final directive before responding.
    parts.append(
        "When working through a non-trivial question, reason step by step inside "
        "<think>...</think> tags before your final response. "
        "Keep the thinking block concise and relevant — skip it for simple replies."
    )

    return "\n\n".join(parts)


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

    async def stream_with_tools(
        self,
        system: str,
        messages: list[dict],
        registry: ToolRegistry,
        trace=None,  # optional RequestTrace from observer.py
    ) -> AsyncIterator[str | ToolEvent]:
        """Agentic loop: tool calls (non-streaming) then final response (streaming).

        Yields ToolEvent objects for tool calls, then str tokens for final response.
        If `trace` is provided, records first_token_ms and per-tool duration_ms.
        """
        all_messages = [{"role": "system", "content": system}] + messages
        tool_schemas = registry.schemas()
        max_rounds = 5
        _start = time.monotonic()

        used_tools = False
        for _ in range(max_rounds):
            response = await self.client.chat(
                model=OLLAMA_MODEL,
                messages=all_messages,
                tools=tool_schemas if tool_schemas else None,
            )

            if not response.message.tool_calls:
                break

            used_tools = True
            all_messages.append(
                {
                    "role": "assistant",
                    "content": response.message.content or "",
                    "tool_calls": [
                        {"function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                        for tc in response.message.tool_calls
                    ],
                }
            )

            for tc in response.message.tool_calls:
                name = tc.function.name
                args = tc.function.arguments
                yield ToolEvent(phase="start", tool_name=name, tool_input=args)

                tool_start = time.monotonic()
                result = await registry.call(name, args)
                tool_ms = int((time.monotonic() - tool_start) * 1000)

                # Record in trace if provided
                if trace is not None:
                    from mlaude.observer import ToolCallRecord
                    trace.tool_calls.append(ToolCallRecord(
                        name=name,
                        args=dict(args),
                        result=result.output,
                        error=result.error,
                        duration_ms=tool_ms,
                    ))
                    # Capture memory writes/deletions
                    if name == "update_memory" and not result.error:
                        trace.memory_writes.append(result.output)
                    elif name == "delete_memory_fact" and not result.error:
                        trace.memory_writes.append(f"[deleted] {result.output}")

                yield ToolEvent(phase="done", tool_name=name, tool_input=args, tool_output=result.output)
                all_messages.append({"role": "tool", "content": result.output})

        if not used_tools and response.message.content:
            # No tools were called — use the already-generated response directly
            # instead of making a second LLM call (saves ~50% latency)
            if trace is not None:
                trace.first_token_ms = int((time.monotonic() - _start) * 1000)
            yield response.message.content
            if trace is not None:
                trace.total_ms = int((time.monotonic() - _start) * 1000)
            return

        # Tools were used — stream a final response incorporating tool results
        first_token = True
        stream_response = await self.client.chat(
            model=OLLAMA_MODEL,
            messages=all_messages,
            stream=True,
        )
        async for chunk in stream_response:
            token = chunk.message.content
            if token:
                if first_token and trace is not None:
                    trace.first_token_ms = int((time.monotonic() - _start) * 1000)
                    first_token = False
                yield token

        if trace is not None:
            trace.total_ms = int((time.monotonic() - _start) * 1000)

    async def generate_title(self, user_msg: str, assistant_msg: str) -> str:
        prompt = (
            f"Summarize this conversation in exactly 4 words in English. "
            f"No punctuation, no quotes, no Chinese, English only.\n\n"
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
