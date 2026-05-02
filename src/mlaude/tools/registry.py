"""Tool registry — auto-discovery, schema management, and dispatch.

Inspired by Hermes ``tools/registry.py``.  Provides a singleton
``ToolRegistry`` that tools self-register into at import time.

Usage in a tool file::

    from mlaude.tools.registry import registry

    def my_tool(param: str, task_id: str = None) -> str:
        return json.dumps({"result": "ok"})

    registry.register(
        name="my_tool",
        toolset="example",
        schema={...},
        handler=lambda args, **kw: my_tool(args.get("param", ""), task_id=kw.get("task_id")),
    )
"""

from __future__ import annotations

import ast
import importlib
import json
import logging
import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def tool_result(data: Any) -> str:
    """Wrap a successful tool result as a JSON string."""
    if isinstance(data, str):
        return data
    return json.dumps(data, default=str)


def tool_error(message: str, **extra: Any) -> str:
    """Wrap an error result as a JSON string."""
    payload = {"error": message}
    payload.update(extra)
    return json.dumps(payload)


# ---------------------------------------------------------------------------
# ToolEntry
# ---------------------------------------------------------------------------


@dataclass
class ToolEntry:
    """A single registered tool."""

    name: str
    toolset: str
    schema: dict
    handler: Callable
    check_fn: Optional[Callable[[], bool]] = None
    requires_env: list[str] = field(default_factory=list)
    is_async: bool = False
    description: str = ""

    def is_available(self) -> bool:
        """Check whether this tool's requirements are met."""
        if self.check_fn is not None:
            try:
                return self.check_fn()
            except Exception:
                return False
        # Check required env vars
        for var in self.requires_env:
            if not os.environ.get(var):
                return False
        return True


# ---------------------------------------------------------------------------
# ToolRegistry
# ---------------------------------------------------------------------------


class ToolRegistry:
    """Singleton tool registry.

    Tools register themselves at module import time via ``registry.register()``.
    The registry provides schema retrieval, dispatch, and availability checks.
    """

    def __init__(self):
        self._tools: dict[str, ToolEntry] = {}
        self._lock = threading.Lock()
        self._discovered = False

    # -- Registration ------------------------------------------------------

    def register(
        self,
        *,
        name: str,
        toolset: str,
        schema: dict,
        handler: Callable,
        check_fn: Callable[[], bool] | None = None,
        requires_env: list[str] | None = None,
        is_async: bool = False,
        description: str = "",
    ) -> None:
        """Register a tool.  Typically called at module level."""
        entry = ToolEntry(
            name=name,
            toolset=toolset,
            schema=schema,
            handler=handler,
            check_fn=check_fn,
            requires_env=requires_env or [],
            is_async=is_async,
            description=description or schema.get("description", ""),
        )
        with self._lock:
            if name in self._tools:
                logger.debug("Re-registering tool: %s", name)
            self._tools[name] = entry
            logger.debug("Registered tool: %s (toolset=%s)", name, toolset)

    def deregister(self, name: str) -> bool:
        """Remove a tool.  Returns True if it existed."""
        with self._lock:
            return self._tools.pop(name, None) is not None

    # -- Querying ----------------------------------------------------------

    def get(self, name: str) -> ToolEntry | None:
        return self._tools.get(name)

    def get_all(self) -> dict[str, ToolEntry]:
        return dict(self._tools)

    def get_available(self) -> dict[str, ToolEntry]:
        """Return only tools whose requirements are met."""
        return {
            name: entry
            for name, entry in self._tools.items()
            if entry.is_available()
        }

    def get_by_toolset(self, toolset: str) -> dict[str, ToolEntry]:
        """Return tools belonging to a specific toolset."""
        return {
            name: entry
            for name, entry in self._tools.items()
            if entry.toolset == toolset
        }

    def list_toolsets(self) -> list[str]:
        """Return all unique toolset names."""
        return sorted({e.toolset for e in self._tools.values()})

    # -- Schema generation -------------------------------------------------

    def get_definitions(
        self,
        enabled_toolsets: list[str] | None = None,
        disabled_toolsets: list[str] | None = None,
    ) -> list[dict]:
        """Return OpenAI-format tool schemas for the active tools.

        Filters by toolset inclusion/exclusion and availability.
        """
        definitions = []
        for name, entry in self._tools.items():
            # Toolset filter
            if enabled_toolsets and entry.toolset not in enabled_toolsets:
                continue
            if disabled_toolsets and entry.toolset in disabled_toolsets:
                continue
            # Availability check
            if not entry.is_available():
                continue

            definitions.append({
                "type": "function",
                "function": entry.schema,
            })
        return definitions

    # -- Dispatch ----------------------------------------------------------

    def dispatch(
        self,
        name: str,
        args: dict[str, Any],
        task_id: str | None = None,
        approval_granted: bool = False,
        enforce_safety: bool = False,
    ) -> str:
        """Execute a tool by name.  Returns a JSON string."""
        entry = self._tools.get(name)
        if entry is None:
            return tool_error(f"Unknown tool: {name}")

        if not entry.is_available():
            missing = [v for v in entry.requires_env if not os.environ.get(v)]
            return tool_error(
                f"Tool '{name}' requirements not met",
                missing_env=missing,
            )

        if enforce_safety:
            from mlaude.safety import policy
            decision = policy.evaluate(name, args, approval_granted=approval_granted)
            if not decision.allowed:
                if decision.requires_approval:
                    return tool_error(
                        "approval_required",
                        tool=name,
                        args=args,
                        reason=decision.reason,
                    )
                return tool_error(
                    f"Tool '{name}' blocked by safety policy",
                    tool=name,
                    reason=decision.reason,
                )

        try:
            result = entry.handler(args, task_id=task_id)
            # Ensure result is a string
            if not isinstance(result, str):
                result = json.dumps(result, default=str)
            return result
        except Exception as e:
            logger.exception("Tool %s failed", name)
            return tool_error(f"Tool '{name}' failed: {e}")

    # -- Discovery ---------------------------------------------------------

    def discover_builtin_tools(self, tools_dir: Path | None = None) -> int:
        """Auto-discover and import tool modules in the tools/ directory.

        Scans for Python files that contain ``registry.register(`` and
        imports them to trigger registration.

        Returns the number of tools discovered.
        """
        if self._discovered:
            return len(self._tools)

        if tools_dir is None:
            tools_dir = Path(__file__).parent

        count_before = len(self._tools)

        for py_file in sorted(tools_dir.glob("*.py")):
            if py_file.name.startswith("_"):
                continue
            if py_file.name == "registry.py":
                continue

            # Quick AST check: does this file call registry.register()?
            try:
                source = py_file.read_text(encoding="utf-8")
                tree = ast.parse(source)
            except Exception:
                continue

            has_register = False
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    func = node.func
                    if isinstance(func, ast.Attribute) and func.attr == "register":
                        has_register = True
                        break

            if not has_register:
                continue

            # Import the module to trigger registration
            module_name = f"mlaude.tools.{py_file.stem}"
            try:
                importlib.import_module(module_name)
                logger.debug("Discovered tool module: %s", module_name)
            except Exception:
                logger.warning("Failed to import tool module: %s", module_name, exc_info=True)

        self._discovered = True
        discovered = len(self._tools) - count_before
        logger.info(
            "Tool discovery complete: %d tools (%d new)",
            len(self._tools), discovered,
        )
        return len(self._tools)

    def reset(self) -> None:
        """Clear all registrations (for testing)."""
        with self._lock:
            self._tools.clear()
            self._discovered = False


# Module-level singleton
registry = ToolRegistry()
