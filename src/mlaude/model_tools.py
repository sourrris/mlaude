"""Tool orchestration layer — bridges the agent loop and the tool registry.

Inspired by Hermes ``model_tools.py``.  Provides:

- ``get_tool_definitions()`` — returns OpenAI-format tool schemas
- ``handle_function_call()`` — dispatches a tool call and returns a JSON string
- ``discover_tools()`` — triggers tool auto-discovery
"""

from __future__ import annotations

import json
import logging
from typing import Any

from mlaude.tools.registry import registry

logger = logging.getLogger(__name__)

_discovered = False


def discover_tools() -> int:
    """Trigger tool auto-discovery.  Idempotent."""
    global _discovered
    if _discovered:
        return len(registry.get_all())
    count = registry.discover_builtin_tools()
    _discovered = True
    return count


def get_tool_definitions(
    enabled_toolsets: list[str] | None = None,
    disabled_toolsets: list[str] | None = None,
    quiet: bool = False,
) -> list[dict]:
    """Return OpenAI-format tool schemas for the currently active tools.

    Triggers discovery on first call.
    """
    discover_tools()
    definitions = registry.get_definitions(
        enabled_toolsets=enabled_toolsets,
        disabled_toolsets=disabled_toolsets,
    )
    if not quiet:
        logger.debug("Providing %d tool definitions", len(definitions))
    return definitions


def handle_function_call(
    function_name: str,
    function_args: dict[str, Any] | str,
    task_id: str | None = None,
) -> str:
    """Dispatch a tool call and return the result as a JSON string.

    Handles argument coercion (string→dict) and error wrapping.
    """
    # Parse string arguments
    if isinstance(function_args, str):
        try:
            function_args = json.loads(function_args)
        except json.JSONDecodeError:
            function_args = {}

    if not isinstance(function_args, dict):
        function_args = {}

    # Coerce common argument types
    function_args = _coerce_args(function_name, function_args)

    # Dispatch via registry
    return registry.dispatch(
        name=function_name,
        args=function_args,
        task_id=task_id,
    )


def get_toolset_for_tool(tool_name: str) -> str | None:
    """Return the toolset name for a given tool."""
    entry = registry.get(tool_name)
    return entry.toolset if entry else None


def check_toolset_requirements(toolset: str) -> dict[str, bool]:
    """Check which tools in a toolset have their requirements met."""
    tools = registry.get_by_toolset(toolset)
    return {name: entry.is_available() for name, entry in tools.items()}


# ---------------------------------------------------------------------------
# Argument coercion
# ---------------------------------------------------------------------------

# Tools that expect integer arguments
_INT_ARGS: dict[str, set[str]] = {
    "read_file": {"start_line", "end_line"},
    "terminal": {"timeout"},
}

# Tools that expect boolean arguments
_BOOL_ARGS: dict[str, set[str]] = {
    "write_file": {"overwrite"},
    "search_files": {"case_sensitive"},
}


def _coerce_args(tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
    """Coerce string arguments to their expected types.

    Models sometimes emit ``"42"`` instead of ``42`` or ``"true"``
    instead of ``true``.  This normalizes common cases.
    """
    int_fields = _INT_ARGS.get(tool_name, set())
    bool_fields = _BOOL_ARGS.get(tool_name, set())

    coerced = dict(args)

    for field_name in int_fields:
        val = coerced.get(field_name)
        if isinstance(val, str):
            try:
                coerced[field_name] = int(val)
            except ValueError:
                pass

    for field_name in bool_fields:
        val = coerced.get(field_name)
        if isinstance(val, str):
            coerced[field_name] = val.lower() in {"true", "1", "yes"}

    return coerced
