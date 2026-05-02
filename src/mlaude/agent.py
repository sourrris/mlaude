"""Core agent loop with tool-calling support.

This is the heart of mlaude — a multi-turn agent that calls LLM APIs using
the OpenAI tool_calls protocol and loops until the model produces a final
text response or the iteration budget is exhausted.

Inspired by the Hermes ``AIAgent`` class (``run_agent.py``).

Usage::

    from mlaude.agent import MLaudeAgent

    agent = MLaudeAgent(base_url="http://localhost:1234", model="gemma4:e4b")
    response = agent.chat("List files in the current directory")
"""

from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from mlaude.model_tools import (
    discover_tools,
    get_tool_definitions,
    handle_function_call,
)
from mlaude.providers.base import BaseProvider
from mlaude.providers.registry import create_provider, detect_provider
from mlaude.settings import (
    DEFAULT_CHAT_MODEL,
    DEFAULT_SYSTEM_PROMPT,
    DEFAULT_TEMPERATURE,
    LLM_BASE_URL,
    MAX_ITERATIONS,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Iteration budget
# ---------------------------------------------------------------------------


class IterationBudget:
    """Thread-safe iteration counter for an agent.

    Each agent gets its own budget capped at ``max_iterations``.
    Subagents (future μ10) get an independent budget.
    """

    def __init__(self, max_total: int):
        self.max_total = max_total
        self._used = 0
        self._lock = threading.Lock()

    def consume(self) -> bool:
        """Try to consume one iteration.  Returns True if allowed."""
        with self._lock:
            if self._used >= self.max_total:
                return False
            self._used += 1
            return True

    def refund(self) -> None:
        """Give back one iteration (e.g. for execute_code turns)."""
        with self._lock:
            if self._used > 0:
                self._used -= 1

    @property
    def used(self) -> int:
        return self._used

    @property
    def remaining(self) -> int:
        with self._lock:
            return max(0, self.max_total - self._used)


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


class MLaudeAgent:
    """Multi-turn tool-calling agent.

    The agent loop follows the OpenAI tool_calls protocol:

    1. Build system prompt + user message + tool schemas.
    2. Call LLM with ``tools=`` parameter.
    3. If response contains ``tool_calls`` → execute each via the dispatcher,
       append tool results as ``role: tool`` messages, and loop.
    4. If response is a plain text reply → return it as the final answer.
    5. Stop when the iteration budget is exhausted (with one grace call to
       let the model wrap up).
    """

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        provider: str | None = None,
        model: str = "",
        max_iterations: int = MAX_ITERATIONS,
        enabled_toolsets: list[str] | None = None,
        disabled_toolsets: list[str] | None = None,
        quiet_mode: bool = False,
        session_id: str | None = None,
        platform: str = "cli",
        system_prompt: str | None = None,
        temperature: float | None = None,
        # Callbacks for display (μ9 CLI will use these)
        on_tool_start: Callable | None = None,
        on_tool_end: Callable | None = None,
        on_token: Callable | None = None,
    ):
        self.base_url = base_url or LLM_BASE_URL
        self.api_key = api_key or os.environ.get("MLAUDE_API_KEY", "")
        self.provider_name = provider or detect_provider(self.base_url)
        self.model = model or DEFAULT_CHAT_MODEL
        self.temperature = temperature if temperature is not None else DEFAULT_TEMPERATURE
        self.max_iterations = max_iterations
        self.enabled_toolsets = enabled_toolsets
        self.disabled_toolsets = disabled_toolsets
        self.quiet_mode = quiet_mode
        self.session_id = session_id or uuid.uuid4().hex
        self.platform = platform
        self.system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT

        # Display callbacks
        self.on_tool_start = on_tool_start
        self.on_tool_end = on_tool_end
        self.on_token = on_token

        # Budget
        self.iteration_budget = IterationBudget(max_iterations)
        self._budget_grace_call = False

        # Interrupt
        self._interrupt_requested = False

        # Provider (auto-detected from base_url or explicit)
        self._provider: BaseProvider = create_provider(
            provider=self.provider_name,
            base_url=self.base_url,
            api_key=self.api_key,
            default_model=self.model,
        )

        # Conversation state
        self._messages: list[dict[str, Any]] = []

        # Discover and wire tool registry
        discover_tools()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def chat(self, message: str) -> str:
        """Simple interface — returns the final response string."""
        result = self.run_conversation(message)
        return result.get("final_response", "")

    def run_conversation(
        self,
        user_message: str,
        system_message: str | None = None,
        conversation_history: list[dict] | None = None,
    ) -> dict:
        """Full interface — returns dict with final_response + messages.

        Args:
            user_message: The user's input text.
            system_message: Override system prompt for this conversation.
            conversation_history: Pre-existing messages to resume from.

        Returns:
            Dict with keys:
                - ``final_response``: The assistant's final text reply.
                - ``messages``: Full message history including tool calls.
                - ``iterations_used``: Number of API calls made.
                - ``stop_reason``: Why the loop ended.
        """
        # System prompt
        sys_prompt = system_message or self.system_prompt
        now = datetime.now(timezone.utc)
        sys_prompt += f"\n\nCurrent UTC time: {now.strftime('%Y-%m-%d %H:%M')}"

        # Build messages
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": sys_prompt},
        ]

        if conversation_history:
            messages.extend(conversation_history)

        messages.append({"role": "user", "content": user_message})

        # Load tool definitions (stub — μ2 will wire the real registry)
        tool_schemas = self._get_tool_definitions()

        # Agent loop
        api_call_count = 0
        stop_reason = "complete"
        final_response = ""

        while True:
            # Budget check
            if not self.iteration_budget.consume():
                if not self._budget_grace_call:
                    # One grace call without tools to let the model wrap up
                    self._budget_grace_call = True
                    tool_schemas = []  # No tools on grace call
                    logger.info(
                        "Budget exhausted (%d/%d) — grace call without tools",
                        self.iteration_budget.used,
                        self.iteration_budget.max_total,
                    )
                else:
                    stop_reason = "budget_exhausted"
                    logger.warning(
                        "Budget exhausted after grace call — stopping"
                    )
                    break

            # Interrupt check
            if self._interrupt_requested:
                stop_reason = "interrupted"
                break

            # Call LLM
            try:
                response = self._call_llm(messages, tool_schemas)
            except Exception as e:
                logger.error("LLM API call failed: %s", e)
                stop_reason = f"error: {e}"
                break

            api_call_count += 1
            assistant_msg = response

            # Check for tool calls
            tool_calls = assistant_msg.get("tool_calls", [])

            if tool_calls:
                # Append assistant message with tool calls
                messages.append(assistant_msg)

                # Execute each tool call
                for tc in tool_calls:
                    tool_name = tc.get("function", {}).get("name", "unknown")
                    tool_args_raw = tc.get("function", {}).get("arguments", "{}")
                    tool_call_id = tc.get("id", f"call_{uuid.uuid4().hex[:8]}")

                    # Parse arguments
                    try:
                        tool_args = json.loads(tool_args_raw) if isinstance(tool_args_raw, str) else tool_args_raw
                    except json.JSONDecodeError:
                        tool_args = {}

                    # Notify display
                    if self.on_tool_start:
                        self.on_tool_start(tool_name, tool_args)

                    # Dispatch
                    tool_result = self._dispatch_tool(tool_name, tool_args)

                    # Notify display
                    if self.on_tool_end:
                        self.on_tool_end(tool_name, tool_result)

                    # Append tool result
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "name": tool_name,
                        "content": tool_result,
                    })

                # Continue loop — model needs to process tool results
                continue

            # No tool calls — this is the final response
            final_response = assistant_msg.get("content", "")
            messages.append({"role": "assistant", "content": final_response})
            break

        # Store conversation state
        self._messages = messages

        return {
            "final_response": final_response,
            "messages": messages,
            "iterations_used": api_call_count,
            "stop_reason": stop_reason,
            "session_id": self.session_id,
        }

    def request_interrupt(self) -> None:
        """Signal the agent loop to stop at the next iteration."""
        self._interrupt_requested = True

    # ------------------------------------------------------------------
    # Tool integration — wired to model_tools.py
    # ------------------------------------------------------------------

    def _get_tool_definitions(self) -> list[dict]:
        """Return tool schemas for the LLM API call."""
        return get_tool_definitions(
            enabled_toolsets=self.enabled_toolsets,
            disabled_toolsets=self.disabled_toolsets,
            quiet=self.quiet_mode,
        )

    def _dispatch_tool(self, name: str, args: dict) -> str:
        """Execute a tool and return the result as a JSON string."""
        return handle_function_call(
            function_name=name,
            function_args=args,
            task_id=self.session_id,
        )

    # ------------------------------------------------------------------
    # LLM communication
    # ------------------------------------------------------------------

    def _call_llm(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
    ) -> dict:
        """Call the LLM via the provider and return an assistant message dict.

        Uses the provider abstraction for automatic format translation
        (e.g. Anthropic Messages API → OpenAI format).
        """
        response = self._provider.chat_completions(
            model=self.model,
            messages=messages,
            tools=tools if tools else None,
            temperature=self.temperature,
        )
        return response.to_message()

    # ------------------------------------------------------------------
    # Streaming (for CLI display)
    # ------------------------------------------------------------------

    def stream_response(self, messages: list[dict]):
        """Stream the final response (no tools) for CLI display.

        Yields dicts with ``content`` and/or ``thinking`` keys.
        Uses the provider's sync stream_chat method.
        """
        for chunk in self._provider.stream_chat(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
        ):
            yield chunk
