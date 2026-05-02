"""Toolset definitions — which tools are available on which platforms.

Inspired by Hermes ``toolsets.py``.
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Core tool list — all tools available in every context
# ---------------------------------------------------------------------------

_MLAUDE_CORE_TOOLS: list[str] = [
    # File operations (μ3)
    "read_file",
    "write_file",
    "patch",
    "search_files",
    # Terminal (μ3)
    "terminal",
    # Web (μ6)
    "web_search",
    "web_extract",
]

# ---------------------------------------------------------------------------
# Toolset composition
# ---------------------------------------------------------------------------

TOOLSETS: dict[str, dict[str, Any]] = {
    # Base toolsets (groups of tools)
    "file": {
        "description": "File read/write/patch/search operations",
        "tools": ["read_file", "write_file", "patch", "search_files"],
    },
    "terminal": {
        "description": "Shell command execution",
        "tools": ["terminal"],
    },
    "web": {
        "description": "Web search and content extraction",
        "tools": ["web_search", "web_extract"],
    },
    "browser": {
        "description": "Browser automation (Playwright)",
        "tools": ["browser_navigate", "browser_snapshot", "browser_click",
                  "browser_type", "browser_scroll"],
    },
    "delegation": {
        "description": "Subagent task delegation",
        "tools": ["delegate_task"],
    },
    "memory": {
        "description": "Persistent cross-session memory",
        "tools": ["memory", "session_search"],
    },
    "skills": {
        "description": "Skill management",
        "tools": ["skills_list", "skill_view", "skill_manage"],
    },
    "planning": {
        "description": "Task planning and tracking",
        "tools": ["todo"],
    },

    # Platform toolsets (composites — what each platform gets)
    "mlaude-cli": {
        "description": "CLI interactive mode",
        "includes": ["file", "terminal", "web", "browser", "delegation",
                     "memory", "skills", "planning"],
    },
    "mlaude-telegram": {
        "description": "Telegram messaging platform",
        "includes": ["file", "terminal", "web", "browser", "memory"],
    },
    "mlaude-whatsapp": {
        "description": "WhatsApp messaging platform",
        "includes": ["file", "terminal", "web", "browser", "memory"],
    },
    "mlaude-email": {
        "description": "Email messaging platform",
        "includes": ["file", "terminal", "web", "memory"],
    },
}


def resolve_toolset(name: str) -> list[str]:
    """Resolve a toolset name to a flat list of tool names.

    Handles nested ``includes`` references recursively.
    """
    seen: set[str] = set()

    def _resolve(ts_name: str) -> list[str]:
        if ts_name in seen:
            return []
        seen.add(ts_name)

        ts = TOOLSETS.get(ts_name)
        if ts is None:
            return []

        result: list[str] = []

        # Direct tools
        for tool_name in ts.get("tools", []):
            if tool_name not in result:
                result.append(tool_name)

        # Included toolsets
        for included in ts.get("includes", []):
            for tool_name in _resolve(included):
                if tool_name not in result:
                    result.append(tool_name)

        return result

    return _resolve(name)


def get_toolset(name: str) -> dict[str, Any] | None:
    """Get a toolset definition by name."""
    return TOOLSETS.get(name)


def validate_toolset(name: str) -> bool:
    """Check whether a toolset name exists."""
    return name in TOOLSETS


def get_platform_tools(platform: str) -> list[str]:
    """Get the tool names available for a platform.

    Maps platform names to toolset names:
    - ``cli`` → ``mlaude-cli``
    - ``telegram`` → ``mlaude-telegram``
    - ``whatsapp`` → ``mlaude-whatsapp``
    - ``email`` → ``mlaude-email``
    """
    toolset_name = f"mlaude-{platform}"
    if toolset_name not in TOOLSETS:
        # Default to CLI toolset
        toolset_name = "mlaude-cli"
    return resolve_toolset(toolset_name)
