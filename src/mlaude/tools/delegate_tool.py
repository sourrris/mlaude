"""Delegate tool — subagent task spawning.

Allows the agent to spawn a subagent with its own iteration budget to
handle a subtask in isolation, then return the result.
"""

from __future__ import annotations

import logging

from mlaude.tools.registry import registry, tool_error, tool_result

logger = logging.getLogger(__name__)


def _delegate_task(
    task: str,
    context: str = "",
    max_iterations: int = 15,
    model: str = "",
    task_id: str = None,
) -> str:
    """Spawn a subagent to handle a subtask."""
    from mlaude.agent import MLaudeAgent

    # Create subagent with limited budget
    subagent = MLaudeAgent(
        model=model or "",  # Inherit default
        max_iterations=max_iterations,
        quiet_mode=True,
        platform="subagent",
    )

    # Build the prompt
    prompt = task
    if context:
        prompt = f"Context:\n{context}\n\nTask:\n{task}"

    try:
        result = subagent.run_conversation(
            user_message=prompt,
            system_message=(
                "You are a focused subagent. Complete the given task efficiently. "
                "Use tools as needed. Be concise in your final response."
            ),
        )

        return tool_result({
            "task": task[:200],
            "response": result.get("final_response", ""),
            "iterations_used": result.get("iterations_used", 0),
            "stop_reason": result.get("stop_reason", ""),
        })

    except Exception as e:
        logger.error("Subagent failed: %s", e)
        return tool_error(f"Subagent failed: {e}")


registry.register(
    name="delegate_task",
    toolset="delegation",
    schema={
        "name": "delegate_task",
        "description": (
            "Delegate a subtask to a separate subagent. The subagent gets its own "
            "iteration budget and tool access. Use this for complex tasks that "
            "benefit from isolated execution."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "Clear description of the subtask to accomplish.",
                },
                "context": {
                    "type": "string",
                    "description": "Additional context for the subagent. Optional.",
                },
                "max_iterations": {
                    "type": "integer",
                    "description": "Max tool-calling iterations for the subagent (default 15).",
                    "default": 15,
                },
            },
            "required": ["task"],
        },
    },
    handler=lambda args, **kw: _delegate_task(
        task=args.get("task", ""),
        context=args.get("context", ""),
        max_iterations=args.get("max_iterations", 15),
        model=args.get("model", ""),
        task_id=kw.get("task_id"),
    ),
)
