"""Structured, bounded subagent delegation."""

from __future__ import annotations

import logging

from mlaude.state import SessionDB
from mlaude.tools.registry import registry, tool_error, tool_result

logger = logging.getLogger(__name__)

_MAX_DELEGATION_DEPTH = 2


def _delegate_task(
    task: str,
    context: str = "",
    expected_output: str = "",
    allowed_toolsets: list[str] | None = None,
    max_iterations: int = 15,
    model: str = "",
    task_id: str | None = None,
) -> str:
    """Spawn a focused subagent with explicit context and bounded depth."""
    from mlaude.agent import MLaudeAgent

    db = SessionDB()
    depth = db.get_session_depth(task_id) if task_id else 0
    if depth >= _MAX_DELEGATION_DEPTH:
        return tool_error(
            "Maximum delegation depth reached.",
            status="blocked",
            stop_reason="depth_limit",
        )

    session_id = db.create_session(
        platform="subagent",
        model=model or "",
        title=f"delegate:{task[:40]}",
        parent_session_id=task_id,
    )
    prompt_parts = []
    if context:
        prompt_parts.append(f"Context:\n{context}")
    if expected_output:
        prompt_parts.append(f"Expected output:\n{expected_output}")
    prompt_parts.append(f"Task:\n{task}")
    prompt = "\n\n".join(prompt_parts)

    try:
        subagent = MLaudeAgent(
            model=model or "",
            max_iterations=max_iterations,
            quiet_mode=True,
            platform="subagent",
            enabled_toolsets=allowed_toolsets,
            session_id=session_id,
            session_db=db,
        )
        result = subagent.run_conversation(
            user_message=prompt,
            system_message=(
                "You are a focused subagent. Complete only the delegated task. "
                "Use only the permitted tools. Be concise and return the requested output."
            ),
        )
        summary = result.get("final_response", "")
        return tool_result(
            {
                "status": "completed" if summary else "incomplete",
                "summary": summary,
                "artifacts": [],
                "suggested_next_step": "Use the summary directly or refine the task.",
                "iterations_used": result.get("iterations_used", 0),
                "stop_reason": result.get("stop_reason", ""),
                "session_id": session_id,
            }
        )
    except Exception as exc:
        logger.error("Subagent failed: %s", exc)
        return tool_error(
            f"Subagent failed: {exc}",
            status="failed",
            summary="",
            artifacts=[],
            suggested_next_step="Retry with narrower context or fewer tools.",
            iterations_used=0,
            stop_reason="error",
        )


registry.register(
    name="delegate_task",
    toolset="delegation",
    schema={
        "name": "delegate_task",
        "description": (
            "Delegate a bounded research, summarization, or comparison subtask to a "
            "focused subagent with explicit context and tool restrictions."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "task": {"type": "string"},
                "context": {"type": "string"},
                "expected_output": {"type": "string"},
                "allowed_toolsets": {"type": "array", "items": {"type": "string"}},
                "max_iterations": {"type": "integer", "default": 15},
            },
            "required": ["task"],
        },
    },
    handler=lambda args, **kw: _delegate_task(
        task=args.get("task", ""),
        context=args.get("context", ""),
        expected_output=args.get("expected_output", ""),
        allowed_toolsets=args.get("allowed_toolsets"),
        max_iterations=int(args.get("max_iterations", 15)),
        model=args.get("model", ""),
        task_id=kw.get("task_id"),
    ),
)
