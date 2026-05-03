"""Core agent loop with tool-calling support.

This is the heart of mlaude — a multi-turn agent that calls LLM APIs using
the OpenAI tool_calls protocol and loops until the model produces a final
text response or the iteration budget is exhausted.

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

from mlaude.capability_router import (
    ROUTES,
    classify_capability_route,
    filter_tools_for_route,
)
from mlaude.model_tools import (
    discover_tools,
    get_tool_definitions,
    handle_function_call,
)
from mlaude.providers.base import BaseProvider
from mlaude.providers.registry import create_provider, detect_provider, get_provider_label
from mlaude.state import SessionDB
from mlaude.settings import (
    DEFAULT_CHAT_MODEL,
    DEFAULT_SYSTEM_PROMPT,
    DEFAULT_TEMPERATURE,
    LLM_BASE_URL,
    MAX_ITERATIONS,
)
from mlaude.toolsets import get_platform_tools, resolve_toolset

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
        reasoning_effort: str | None = None,
        session_db: SessionDB | None = None,
        # Callbacks for display (μ9 CLI will use these)
        on_tool_start: Callable | None = None,
        on_tool_end: Callable | None = None,
        on_token: Callable | None = None,
        on_approval_request: Callable[[str, dict[str, Any]], bool] | None = None,
        on_event: Callable[[dict[str, Any]], None] | None = None,
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
        self.reasoning_effort = reasoning_effort
        self.session_db = session_db

        # Display callbacks
        self.on_tool_start = on_tool_start
        self.on_tool_end = on_tool_end
        self.on_token = on_token
        self.on_approval_request = on_approval_request
        self.on_event = on_event

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
        self._platform_tools = get_platform_tools(platform)

        # Discover and wire tool registry
        discover_tools()

        if self.session_db and self.session_db.get_session(self.session_id) is None:
            self.session_db.create_session(
                session_id=self.session_id,
                platform=self.platform,
                model=self.model,
            )

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
        self.iteration_budget = IterationBudget(self.max_iterations)
        self._budget_grace_call = False

        sys_prompt = system_message or self.system_prompt
        now = datetime.now(timezone.utc)
        sys_prompt += f"\n\nCurrent UTC time: {now.strftime('%Y-%m-%d %H:%M')}"
        route = classify_capability_route(user_message)
        if route.system_prompt_suffix:
            sys_prompt += f"\n\n{route.system_prompt_suffix}"

        # Build messages
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": sys_prompt},
        ]

        if conversation_history:
            messages.extend(conversation_history)

        messages.append({"role": "user", "content": user_message})
        self._persist_message(role="user", content=user_message)

        tool_schemas = self._get_tool_definitions(route.name)

        # Agent loop
        api_call_count = 0
        stop_reason = "complete"
        final_response = ""
        latest_usage: dict[str, int] = {}
        turn_usage = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }
        response_model = self.model

        while True:
            self._emit_event("status.update", busy=True, detail="Calling model")
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
            if hasattr(response, "to_message"):
                assistant_msg = response.to_message()
                usage = getattr(response, "usage", {}) or {}
                response_model = getattr(response, "model", "") or response_model
            else:
                assistant_msg = response
                usage = {}
            latest_usage = {
                "prompt_tokens": int(usage.get("prompt_tokens", 0) or 0),
                "completion_tokens": int(usage.get("completion_tokens", 0) or 0),
                "total_tokens": int(usage.get("total_tokens", 0) or 0),
            }
            for key in turn_usage:
                turn_usage[key] += latest_usage.get(key, 0)
            if self.session_db and usage.get("total_tokens"):
                self.session_db.update_session_tokens(
                    self.session_id,
                    usage.get("total_tokens", 0),
                )

            # Check for tool calls
            tool_calls = assistant_msg.get("tool_calls", [])

            if tool_calls:
                # Append assistant message with tool calls
                messages.append(assistant_msg)
                self._persist_message(
                    role="assistant",
                    content=assistant_msg.get("content", "") or "",
                    tool_calls=tool_calls,
                    reasoning=assistant_msg.get("reasoning"),
                    tokens=usage.get("total_tokens", 0),
                )
                if assistant_msg.get("reasoning"):
                    self._emit_event(
                        "reasoning.available",
                        content=assistant_msg.get("reasoning", ""),
                    )

                # Execute each tool call
                for tc in tool_calls:
                    tool_name = tc.get("function", {}).get("name", "unknown")
                    tool_args_raw = tc.get("function", {}).get("arguments", "{}")
                    tool_call_id = tc.get("id", f"call_{uuid.uuid4().hex[:8]}")

                    # Parse arguments
                    try:
                        tool_args = (
                            json.loads(tool_args_raw)
                            if isinstance(tool_args_raw, str)
                            else tool_args_raw
                        )
                    except json.JSONDecodeError:
                        tool_args = {}

                    # Notify display
                    if self.on_tool_start:
                        self.on_tool_start(tool_name, tool_args)

                    # Dispatch
                    tool_result = self._dispatch_tool(tool_name, tool_args)
                    tool_result = self._maybe_resume_approved_tool(tool_name, tool_args, tool_result)

                    # Notify display
                    if self.on_tool_end:
                        self.on_tool_end(tool_name, tool_result)

                    # Append tool result
                    tool_message = {
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "name": tool_name,
                        "content": tool_result,
                    }
                    messages.append(tool_message)
                    self._persist_message(
                        role="tool",
                        content=tool_result,
                        tool_call_id=tool_call_id,
                        tool_name=tool_name,
                    )

                # Continue loop — model needs to process tool results
                continue

            # No tool calls — this is the final response
            final_response = assistant_msg.get("content", "")
            messages.append(assistant_msg)
            self._persist_message(
                role="assistant",
                content=final_response,
                reasoning=assistant_msg.get("reasoning"),
                tokens=usage.get("total_tokens", 0),
            )
            if assistant_msg.get("reasoning"):
                self._emit_event(
                    "reasoning.available",
                    content=assistant_msg.get("reasoning", ""),
                )
            if final_response:
                self._emit_event("message.complete", role="assistant", content=final_response)
            break

        # Store conversation state
        self._messages = messages
        self._emit_event("status.update", busy=False, detail=stop_reason)

        return {
            "final_response": final_response,
            "messages": messages,
            "iterations_used": api_call_count,
            "stop_reason": stop_reason,
            "session_id": self.session_id,
            "route": route.name,
            "latest_usage": latest_usage,
            "turn_usage": turn_usage,
            "provider_label": get_provider_label(self.provider_name),
            "model_label": response_model or self.model,
        }

    def request_interrupt(self) -> None:
        """Signal the agent loop to stop at the next iteration."""
        self._interrupt_requested = True
        self._emit_event("status.update", busy=True, detail="Interrupt requested")

    # ------------------------------------------------------------------
    # Tool integration — wired to model_tools.py
    # ------------------------------------------------------------------

    def _get_tool_definitions(self, route_name: str = "local_code") -> list[dict]:
        """Return tool schemas for the LLM API call."""
        allowed_tools = self._resolve_allowed_tools(route_name)
        return get_tool_definitions(
            enabled_toolsets=self.enabled_toolsets,
            disabled_toolsets=self.disabled_toolsets,
            allowed_tool_names=allowed_tools,
            quiet=self.quiet_mode,
        )

    def _dispatch_tool(
        self,
        name: str,
        args: dict,
        approval_granted: bool = False,
    ) -> str:
        """Execute a tool and return the result as a JSON string."""
        return handle_function_call(
            function_name=name,
            function_args=args,
            task_id=self.session_id,
            approval_granted=approval_granted,
        )

    # ------------------------------------------------------------------
    # LLM communication
    # ------------------------------------------------------------------

    def _call_llm(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
    ):
        """Call the LLM via the provider and return the normalized response.

        Uses the provider abstraction for automatic format translation
        (e.g. Anthropic Messages API → OpenAI format).
        """
        if not tools and self.on_event and self._provider.supports_streaming_text:
            chunks: list[str] = []
            reasoning: list[str] = []
            for chunk in self._provider.stream_chat(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                reasoning_effort=self.reasoning_effort,
            ):
                content = str(chunk.get("content", "") or "")
                thinking = str(chunk.get("thinking", "") or "")
                if content:
                    chunks.append(content)
                    self._emit_event("message.delta", role="assistant", delta=content)
                if thinking:
                    reasoning.append(thinking)
                    self._emit_event("reasoning.delta", delta=thinking)
            final_content = "".join(chunks)
            final_reasoning = "".join(reasoning)
            return self._provider.build_streaming_response(
                content=final_content,
                reasoning=final_reasoning,
            )
        return self._provider.chat_completions(
            model=self.model,
            messages=messages,
            tools=tools if tools else None,
            temperature=self.temperature,
            reasoning_effort=self.reasoning_effort,
        )

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
            reasoning_effort=self.reasoning_effort,
        ):
            yield chunk

    def _resolve_allowed_tools(self, route_name: str) -> list[str]:
        allowed_tools = list(self._platform_tools)

        if self.enabled_toolsets:
            allowed_set: set[str] = set()
            for toolset_name in self.enabled_toolsets:
                allowed_set.update(resolve_toolset(toolset_name))
            allowed_tools = [name for name in allowed_tools if name in allowed_set]

        if self.disabled_toolsets:
            disabled_set: set[str] = set()
            for toolset_name in self.disabled_toolsets:
                disabled_set.update(resolve_toolset(toolset_name))
            allowed_tools = [name for name in allowed_tools if name not in disabled_set]

        route = ROUTES.get(route_name, ROUTES["local_code"])
        return filter_tools_for_route(route, allowed_tools)

    def _persist_message(
        self,
        *,
        role: str,
        content: str = "",
        tool_calls: list[dict[str, Any]] | None = None,
        tool_call_id: str | None = None,
        tool_name: str | None = None,
        reasoning: str | None = None,
        tokens: int = 0,
    ) -> None:
        if not self.session_db:
            return
        self.session_db.add_message(
            session_id=self.session_id,
            role=role,
            content=content,
            tool_calls=tool_calls,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            reasoning=reasoning,
            tokens=tokens,
        )

    def _maybe_resume_approved_tool(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
        tool_result: str,
    ) -> str:
        if not self.on_approval_request:
            return tool_result
        try:
            payload = json.loads(tool_result)
        except Exception:
            return tool_result
        if payload.get("error") != "approval_required":
            return tool_result
        if not self.on_approval_request(tool_name, tool_args):
            return tool_result
        return self._dispatch_tool(tool_name, tool_args, approval_granted=True)

    def _emit_event(self, event_type: str, **payload: Any) -> None:
        if self.on_event:
            self.on_event({"type": event_type, **payload})
